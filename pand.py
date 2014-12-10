#!/usr/bin/python
import os,argparse,sys
import xml.etree.ElementTree as ET
from subprocess import call,check_output
import random

def get_package_and_activity(folder):
    package = None
    activity = None
    try:
        manifest_path = os.path.join(folder,'AndroidManifest.xml')
        if os.path.isfile(manifest_path):
            tree = ET.parse(manifest_path)
            package = tree.getroot().attrib['package']
            app = tree.getroot().find('application')
            for act in app.iterfind('activity'):
                for intent in act.iterfind('intent-filter'):
                    for action in intent.iterfind('action'):
                        for key,value in action.attrib.iteritems():
                            if key.endswith('name') and value == 'android.intent.action.MAIN':
                                activity = act.attrib['{http://schemas.android.com/apk/res/android}name']
                                raise Exception('found activity %s'%activity)


    except Exception as e:
        print e
        pass
    return (package,activity)

def get_app_name(folder):
    build_path = os.path.join(folder,'build.xml')
    if os.path.isfile(build_path):
       tree = ET.parse(build_path) 
       return tree.getroot().attrib['name']
    return None

def detect_changes(f,folder):
    if os.path.isfile(f) and os.path.isdir(folder):
        t0 = os.path.getmtime(f)
        for root,dirs,files in os.walk(folder):
            for thing in files:
                name,ext = os.path.splitext(thing)
                if ext.lower() in ['.xml','.java','.aidl']:
                    if os.path.getmtime(os.path.join(root,thing))>t0:
                        print 'changes detected: %s'%(thing)
                        return True
                    else:
                        pass
    else:
        return True
    return False

def do_build(project,source,**args):
    apk_file = os.path.join(project,"bin/%s-debug.apk"%(get_app_name(project)))
    BUILD_PROP = 'bin/build.prop'
    build_prop = os.path.join(project,BUILD_PROP)
    skip = (not detect_changes(build_prop,source)) and  os.path.isfile(apk_file)
    path = os.getcwd()
    toraise = None
    try:
        os.chdir(project)
        if not skip:
            if os.path.isfile(apk_file):
                try:
                    os.remove(apk_file)
                except:
                    pass

            if 'env' in args:
                env = args['env']
                for key,value in env.iteritems():
                    os.environ[key] = value
            call(['ant','debug'])
        if os.path.isfile(apk_file):
            print 'build ok'
        else:
            raise Exception('failed to build apk : %s'%(apk_file))
    finally:
        os.chdir(path)

def do_run(project,source,**args):
    apk_file = os.path.join(project,"bin/%s-debug.apk"%(get_app_name(project)))
    if not os.path.isfile(apk_file):
        do_build(project,source,**args)

    path = os.getcwd()
    try:
        os.chdir(project)
        print 'build ok, installing'
        call(['adb','install','-r',apk_file]) 
        package,activity = get_package_and_activity(project)
        print 'package[%s],activity[%s]'%(package,activity)
        if package is not None and activity is not None:
            call(['adb','shell','am','start','-n','%s/%s'%(package,activity)])
            grep = check_output(['adb','shell','set `ps|grep %s|grep -v :`;echo $2'%(package)]).strip()
            cmd = 'adb logcat|grep %s'%(grep)
            print cmd
            call([cmd],shell=True)
        else:
            print 'failed to determine package and activity'
    finally:
        os.chdir(path)

def do_adb(project,source,**args):
    package,activity = get_package_and_activity(project)
    print 'package[%s],activity[%s]'%(package,activity)
    if package is not None and activity is not None:
        grep = check_output(['adb','shell','set `ps|grep %s|grep -v :`;echo $2'%(package)]).strip()
        cmd = 'adb logcat|grep %s'%(grep)
        print cmd
        call([cmd],shell=True)
    else:
        print 'failed to determine package and activity'


def do_debug(project,source,**args):
    apk_file = os.path.join(project,"bin/%s-debug.apk"%(get_app_name(project)))
    if not os.path.isfile(apk_file):
        do_build(project,source,**args)
    BUILD_PROP = 'bin/build.prop'
    build_prop = os.path.join(project,BUILD_PROP)
    skip = not detect_changes(build_prop,source)

    path = os.getcwd()
    try:
        os.chdir(project)
           
        print 'build ok, installing'
        call(['adb','install','-r',apk_file]) 
        package,activity = get_package_and_activity(project)
        print 'package[%s],activity[%s]'%(package,activity)
        if package is not None and activity is not None:
            call(['adb','shell','am','start','-n','%s/%s'%(package,activity)])
            pid = check_output(['adb','shell','set `ps|grep %s|grep -v :`;echo $2'%(package)]).strip()
            print 'forwarding debugg port %s'%(pid)
            print check_output(['adb','forward','tcp:19438','jdwp:%s'%(pid)])
            print 'connecting jdb'
            call(['jdb -attach localhost:19438'],shell=True)

            print 'failed to determine package and activity'
    finally:
        os.chdir(path)

def do_clean(project,source,**args):
    path = os.getcwd()
    try:
        os.chdir(project)
        if 'env' in args:
            env = args['env']
            for key,value in env.iteritems():
                os.environ[key] = value
        cs = call(['ant','clean'])
    finally:
        os.chdir(path)

def do_compile(project,source,**args):
    COMPILE_PROP = 'bin/compile.prop'
    compile_prop = os.path.join(project,COMPILE_PROP)
    skip = not detect_changes(compile_prop,source)
        
    if skip:
        print 'no changes detected, compile skipped'
        return

    path = os.getcwd()
    try:
        os.chdir(project)
        rules_xml = os.path.join(project,'custom_rules.xml')
        tree = None
        root = None
        if os.path.isfile(rules_xml):
            try:
                tree = ET.parse(rules_xml)
                root = tree.getroot()
            except Exception as e:
                tree = None
                print 'error reading rules %s'%(e)

        if tree is None:
            root = ET.Element('project')
            root.attrib['name'] = 'build-rules'
            root.attrib['default'] = 'help'
            tree = ET.ElementTree(root)

        compile_target_ready = False
            
        for child in root:
            if child.tag == 'target' and child.attrib['name'] == 'compile':
                compile_target_ready = True

        if not compile_target_ready:
            ET.SubElement(root,'target',{'name':'compile','depends':'-set-debug-mode,-compile'})
            tree.write(rules_xml)

        if 'env' in args:
            env = args['env']
            for key,value in env.iteritems():
                os.environ[key] = value
        cs = call(['ant','compile'])
        if cs == 0:
            with open(COMPILE_PROP,'w') as prop:
                prop.write('compile succeed')
    finally:
        os.chdir(path)

def check_project(p):
    if not os.path.isabs(p): 
        p = os.path.join(os.getcwd(),p)
    if not os.path.isdir(p) or  not os.path.isfile(os.path.join(p,'AndroidManifest.xml')):
        raise argparse.ArgumentTypeError('invalid project folder')
    return p 

def check_source(p):
    if not os.path.isabs(p): 
        p = os.path.join(os.getcwd(),p)
    if not os.path.isdir(p):
        raise argparse.ArgumentTypeError('invalid source folder')
    return p 


def do_idle(project,source):
    pass

def do_config(project,source):
    print 'What is your project path?'
    while True:
        p = sys.stdin.readline().strip()
        try:
            p = check_project(p)
            break;
        except:
            print 'Dude, this path looks not like a project folder to me. I will give you one more chance to make it right:'
            pass
    print 'Where do you want me to scan for changes?'
    while True:
        s = sys.stdin.readline().strip()
        try:
            s = check_source(s)
            break;
        except:
            print 'Man, we need a folder. Tell me again now:'
            pass
    with open('.pand','w') as f:
        f.write('project=%s\n'%(p))
        f.write('source=%s\n'%(s))
        print 'I am good. Bye then!'
        exit(0)

if __name__ == '__main__':
    #parse the arguments
    cmds = []
    config_file = os.path.join(os.getcwd(),'.pand')
    if not os.path.isfile(config_file):
        print 'Howdy Dude, tell me something before we can start,ready?'
        print '[Y/N]'
        while True:
            choice = sys.stdin.readline().strip()
            if choice.lower() in ['y','yes','yep','yeah']:
                do_config(None,None)
                break
            elif choice.lower() in ['n','no','nuh','nope']:
                break
            else:
                print 'Speak English![Y/N]'
    try:
        if len(sys.argv) == 1:
            cmds = ['compile']
        else:
            cmds = sys.argv[1].split(',')
        default_p = '.'
        default_s = '.'
        if os.path.isfile(config_file):
            with open(config_file,'r') as f:
                lines = f.readlines()
                for line in lines:
                    try:
                        key,value = line.split('=',2)
                        key = key.strip()
                        value = value.strip()
                        if key == 'project':
                            default_p = check_project(value)
                        elif key == 'source':
                            default_s = check_source(value)
                    except:
                        pass
        for cmd in cmds:
            if 'do_%s'%(cmd) not in globals():
                trash_talks = ['what the heck is %s?','Man! I know not what %s is','Seriously, what do you mean by %s?']
                random.seed()
                raise Exception(trash_talks[random.randrange(len(trash_talks))]%(cmd))

        if len(sys.argv) >= 3:
            project = sys.argv[2]
        else:
            project = default_p
        project = check_project(project)
        

        if len(sys.argv) >= 4:
            source = sys.argv[3]
        else:
            source = default_s
        source = check_source(source)

        for cmd in cmds:
            globals()['do_%s'%(cmd)](project,source)
    except Exception as e:
        print e
        if 'config' in cmds and len(cmds) == 1:
            try:
                do_config(None,None)
            except Exception as ce:
                print ce
                exit(1)
        else:
            exit(1)    
    