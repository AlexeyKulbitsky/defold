#!/usr/bin/env python

import os, sys, shutil, zipfile, re
import optparse, subprocess
from tarfile import TarFile
from os.path import join, basename, relpath
from glob import glob

"""
Build utility for installing external packages, building engine, editor and cr
Run build.py --help for help
"""

PACKAGES_ALL="protobuf-2.3.0 waf-1.5.9 gtest-1.2.1 vectormathlibrary-r1649 nvidia-texture-tools-2.0.6 PIL-1.1.6 junit-4.6 protobuf-java-2.3.0 openal-1.1 maven-3.0.1 vecmath vpx-v0.9.7-p1 asciidoc-8.6.7".split()
PACKAGES_HOST="protobuf-2.3.0 gtest-1.2.1 glut-3.7.6 cg-2.1 nvidia-texture-tools-2.0.6 PIL-1.1.6 openal-1.1 PVRTexToolCL-2.08.28.0634 vpx-v0.9.7-p1".split()
PACKAGES_EGGS="protobuf-2.3.0-py2.5.egg pyglet-1.1.3-py2.5.egg gdata-2.0.6-py2.6.egg Jinja2-2.6-py2.6.egg".split()
PACKAGES_IOS="protobuf-2.3.0 gtest-1.2.1".split()

class Configuration(object):
    def __init__(self, dynamo_home = None,
                 target_platform = None,
                 eclipse_home = None,
                 skip_tests = False,
                 skip_codesign = False,
                 no_colors = False,
                 archive_path = None,
                 set_version = None):

        if sys.platform == 'win32':
            home = os.environ['USERPROFILE']
        else:
            home = os.environ['HOME']

        self.dynamo_home = dynamo_home if dynamo_home else join(os.getcwd(), 'tmp', 'dynamo_home')
        self.eclipse_home = eclipse_home if eclipse_home else join(home, 'eclipse')
        self.defold_root = os.getcwd()
        self.host = 'linux' if sys.platform == 'linux2' else sys.platform
        self.target_platform = target_platform if target_platform else self.host
        self.skip_tests = skip_tests
        self.skip_codesign = skip_codesign
        self.no_colors = no_colors
        self.archive_path = archive_path
        self.set_version = set_version

        self._create_common_dirs()

    def _create_common_dirs(self):
        for p in ['ext/lib/python', 'lib/python', 'share']:
            self._mkdirs(join(self.dynamo_home, p))

    def _mkdirs(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def _log(self, msg):
        print msg
        sys.stdout.flush()
        sys.stderr.flush()

    def distclean(self):
        shutil.rmtree(self.dynamo_home)
        # Recreate dirs
        self._create_common_dirs()

    def _extract_tgz(self, file, path):
        self._log('Extracting %s to %s' % (file, path))
        version = sys.version_info
        # Avoid a bug in python 2.7 (fixed in 2.7.2) related to not being able to remove symlinks: http://bugs.python.org/issue10761
        if self.host == 'linux' and version[0] == 2 and version[1] == 7 and version[2] < 2:
            self.exec_command(['tar', 'xfz', file], cwd = path)
        else:
            tf = TarFile.open(file, 'r:gz')
            tf.extractall(path)
            tf.close()

    def _copy(self, src, dst):
        self._log('Copying %s -> %s' % (src, dst))
        shutil.copy(src, dst)

    def install_ext(self):
        ext = join(self.dynamo_home, 'ext')
        def make_path(platform):
            return join(self.defold_root, 'packages', p) + '-%s.tar.gz' % platform

        for p in PACKAGES_ALL:
            self._extract_tgz(make_path('common'), ext)

        for p in PACKAGES_HOST:
            self._extract_tgz(make_path(self.host), ext)

        for p in PACKAGES_IOS:
            self._extract_tgz(make_path('armv6-darwin'), ext)

        for egg in glob(join(self.defold_root, 'packages', '*.egg')):
            self._log('Installing %s' % basename(egg))
            self.exec_command(['easy_install', '-q', '-d', join(ext, 'lib', 'python'), '-N', egg])

        for n in 'waf_dynamo.py waf_content.py'.split():
            self._copy(join(self.defold_root, 'share', n), join(self.dynamo_home, 'lib/python'))

        for n in 'valgrind-libasound.supp valgrind-libdlib.supp valgrind-python.supp engine_profile.mobileprovision'.split():
            self._copy(join(self.defold_root, 'share', n), join(self.dynamo_home, 'share'))

    def _git_sha1(self, dir = '.'):
        process = subprocess.Popen('git log --oneline -n1'.split(), stdout = subprocess.PIPE)
        out, err = process.communicate()
        if process.returncode != 0:
            sys.exit(process.returncode)

        line = out.split('\n')[0].strip()
        sha1 = line.split()[0]
        return sha1

    def is_cross_platform(self):
        return self.target_platform in ['armv6-darwin']

    def archive_engine(self):
        exe_ext = '.exe' if self.target_platform == 'win32' else ''
        host, path = self.archive_path.split(':', 1)
        sha1 = self._git_sha1()
        self.exec_command(['ssh', host, 'mkdir -p %s' % path])
        dynamo_home = self.dynamo_home
        # TODO: Ugly win fix, make better (https://defold.fogbugz.com/default.asp?1066)
        if self.target_platform == 'win32':
            dynamo_home = dynamo_home.replace("\\", "/")
            dynamo_home = "/" + dynamo_home[:1] + dynamo_home[2:]

        if self.is_cross_platform():
            # When cross compiling the engine is located
            # under PREFIX/bin/platform/...
            bin_dir = self.target_platform
        else:
            bin_dir = ''

        self.exec_command(['scp', join(dynamo_home, 'bin', bin_dir, 'dmengine' + exe_ext),
                           '%s/dmengine%s.%s' % (self.archive_path, exe_ext, sha1)])
        self.exec_command(['ssh', host,
                           'ln -sfn dmengine%s.%s %s/dmengine%s' % (exe_ext, sha1, path, exe_ext)])

    def build_engine(self):
        skip_tests = '--skip-tests' if self.skip_tests or self.target_platform != self.host else ''
        skip_codesign = '--skip-codesign' if self.skip_codesign else ''
        libs="dlib ddf particle glfw graphics hid input physics resource lua script render gameobject gui sound gamesys tools record engine".split()

        # NOTE: We run waf using python <PATH_TO_WAF>/waf as windows don't understand that waf is an executable
        if self.target_platform != self.host:
            self._log('Building dlib for host platform')
            cwd = join(self.defold_root, 'engine/dlib')
            cmd = 'python %s/ext/bin/waf configure --prefix=%s %s %s distclean configure build install' % (self.dynamo_home, self.dynamo_home, skip_tests, skip_codesign)
            self.exec_command(cmd.split(), cwd = cwd)

        for lib in libs:
            self._log('Building %s' % lib)
            cwd = join(self.defold_root, 'engine/%s' % lib)
            cmd = 'python %s/ext/bin/waf configure --prefix=%s --platform=%s %s %s distclean configure build install' % (self.dynamo_home, self.dynamo_home, self.target_platform, skip_tests, skip_codesign)
            self.exec_command(cmd.split(), cwd = cwd)

    def build_docs(self):
        skip_tests = '--skip-tests' if self.skip_tests or self.target_platform != self.host else ''
        self._log('Building docs')
        cwd = join(self.defold_root, 'engine/docs')
        cmd = 'python %s/ext/bin/waf configure --prefix=%s %s distclean configure build install' % (self.dynamo_home, self.dynamo_home, skip_tests)
        self.exec_command(cmd.split(), cwd = cwd)

    def test_cr(self):
        for plugin in ['common', 'luaeditor', 'builtins']:
            self.exec_command(['ln', '-sfn',
                               self.dynamo_home,
                               join(self.defold_root, 'com.dynamo.cr', 'com.dynamo.cr.%s/DYNAMO_HOME' % plugin)])

        cwd = join(self.defold_root, 'com.dynamo.cr', 'com.dynamo.cr.parent')
        self.exec_command([join(self.dynamo_home, 'ext/share/maven/bin/mvn'), 'clean', 'verify'],
                          cwd = cwd)

    def _get_cr_builddir(self, product):
        return join(os.getcwd(), 'tmp', product)

    def build_server(self):
        build_dir = self._get_cr_builddir('server')
        self._build_cr('server', build_dir)

    def build_editor(self):
        build_dir = self._get_cr_builddir('editor')

        root_properties = '''root.linux.gtk.x86=absolute:${buildDirectory}/plugins/com.dynamo.cr.editor/jre_linux/
root.linux.gtk.x86.permissions.755=jre/'''
        self._build_cr('editor', build_dir, root_properties = root_properties)

        # NOTE:
        # Due to bug https://bugs.eclipse.org/bugs/show_bug.cgi?id=300812
        # we cannot add jre to p2 on win32
        # The jre is explicitly bundled instead
        prefix = 'Defold'
        zip = join(build_dir, 'I.Defold/Defold-win32.win32.x86.zip')
        jre_root = join(build_dir, 'plugins/com.dynamo.cr.editor/jre_win32')
        zip = zipfile.ZipFile(zip, 'a')

        for root, dirs, files in os.walk(jre_root):
            for f in files:
                full = join(root, f)
                rel = relpath(full, jre_root)
                with open(full, 'rb') as file:
                    data = file.read()
                    path = join(prefix, rel)
                    zip.writestr(path, data)
        zip.close()

    def _archive_cr(self, product, build_dir):
        host, path = self.archive_path.split(':', 1)
        self.exec_command(['ssh', host, 'mkdir -p %s' % path])
        for p in glob(join(build_dir, 'I.*/*.zip')):
            self.exec_command(['scp', p, self.archive_path])
        self.exec_command(['tar', '-C', build_dir, '-cz', '-f', join(build_dir, '%s_repository.tgz' % product), 'repository'])
        self.exec_command(['scp', join(build_dir, '%s_repository.tgz' % product), self.archive_path])

    def archive_editor(self):
        build_dir = self._get_cr_builddir('editor')
        self._archive_cr('editor', build_dir)

    def archive_server(self):
        build_dir = self._get_cr_builddir('server')
        self._archive_cr('server', build_dir)

    def _build_cr(self, product, build_dir, root_properties = None):
        equinox_version = '1.2.0.v20110502'

        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        os.makedirs(join(build_dir, 'plugins'))
        os.makedirs(join(build_dir, 'features'))

        if root_properties:
            with open(join(build_dir, 'root.properties'), 'wb') as f:
                f.write(root_properties)

        workspace = join(os.getcwd(), 'tmp', 'workspace_%s' % product)
        if os.path.exists(workspace):
            shutil.rmtree(workspace)
        os.makedirs(workspace)

        for p in glob(join(self.defold_root, 'com.dynamo.cr', '*')):
            dst = join(build_dir, 'plugins', basename(p))
            self._log('Copying .../%s -> %s' % (basename(p), dst))
            shutil.copytree(p, dst)

        args = ['java',
                '-Xms256m',
                '-Xmx1500m',
                '-jar',
                '%s/plugins/org.eclipse.equinox.launcher_%s.jar' % (self.eclipse_home, equinox_version),
                '-application', 'org.eclipse.ant.core.antRunner',
                '-buildfile', 'ci/cr/build_%s.xml' % product,
                '-DbaseLocation=%s' % self.eclipse_home,
                '-DbuildDirectory=%s' % build_dir,
                '-DbuildProperties=%s' % join(os.getcwd(), 'ci/cr/%s.properties' % product),
                '-data', workspace]

        self.exec_command(args)

    def bump(self):
        sha1 = self._git_sha1()

        with open('VERSION', 'r') as f:
            current = f.readlines()[0].strip()

        if self.set_version:
            new_version = self.set_version
        else:
            lst = map(int, current.split('.'))
            lst[-1] += 1
            new_version = '.'.join(map(str, lst))

        with open('VERSION', 'w') as f:
            f.write(new_version)

        with open('com.dynamo.cr/com.dynamo.cr.editor/src/com/dynamo/cr/editor/Activator.java', 'a+') as f:
            f.seek(0)
            activator = f.read()

            activator = re.sub('public static final String VERSION = "[0-9\.]+";', 'public static final String VERSION = "%s";' % new_version, activator)
            activator = re.sub('public static final String VERSION_SHA1 = ".*?";', 'public static final String VERSION_SHA1 = "%s";' % sha1, activator)
            f.truncate(0)
            f.write(activator)


        with open('engine/engine/src/engine_version.h', 'a+') as f:
            f.seek(0)
            engine_version = f.read()

            engine_version = re.sub('const char\* VERSION = "[0-9\.]+";', 'const char* VERSION = "%s";' % new_version, engine_version)
            engine_version = re.sub('const char\* VERSION_SHA1 = ".*?";', 'const char* VERSION_SHA1 = "%s";' % sha1, engine_version)
            f.truncate(0)
            f.write(engine_version)


        print 'Bumping engine version from %s to %s' % (current, new_version)
        print 'Review changes and commit'

    def exec_command(self, arg_list, **kwargs):
        env = dict(os.environ)

        ld_library_path = 'DYLD_LIBRARY_PATH' if self.host == 'darwin' else 'LD_LIBRARY_PATH'
        env[ld_library_path] = os.path.pathsep.join(['%s/lib' % self.dynamo_home,
                                                     '%s/ext/lib/%s' % (self.dynamo_home, self.host)])

        env['PYTHONPATH'] = os.path.pathsep.join(['%s/lib/python' % self.dynamo_home,
                                                  '%s/ext/lib/python' % self.dynamo_home])

        env['DYNAMO_HOME'] = self.dynamo_home

        paths = os.path.pathsep.join(['%s/bin' % self.dynamo_home,
                                      '%s/ext/bin' % self.dynamo_home,
                                      '%s/ext/bin/%s' % (self.dynamo_home, self.host)])

        env['PATH'] = paths + os.path.pathsep + env['PATH']

        env['MAVEN_OPTS'] = '-Xms256m -Xmx700m -XX:MaxPermSize=1024m'

        # Force 32-bit python 2.6 on darwin. We should perhaps switch to 2.7 soon?
        env['VERSIONER_PYTHON_PREFER_32_BIT'] = 'yes'
        env['VERSIONER_PYTHON_VERSION'] = '2.6'

        if self.no_colors:
            env['NOCOLOR'] = '1'
            env['GTEST_COLOR'] = 'no'

        process = subprocess.Popen(arg_list, env = env, **kwargs)
        process.wait()
        if process.returncode != 0:
            sys.exit(process.returncode)

if __name__ == '__main__':
    usage = '''usage: %prog [options] command(s)

Commands:
distclean       - Removes the DYNAMO_HOME folder
install_ext     - Install external packages
build_engine    - Build engine
archive_engine  - Archive engine to path specified with --archive-path
test_cr         - Test editor and server
build_server    - Build server
build_editor    - Build editor
archive_editor  - Archive editor to path specified with --archive-path
archive_server  - Archive server to path specified with --archive-path
build_docs      - Build documentation
bump            - Bump version number

Multiple commands can be specified'''

    parser = optparse.OptionParser(usage)

    parser.add_option('--eclipse-home', dest='eclipse_home',
                      default = None,
                      help = 'Eclipse directory')

    parser.add_option('--platform', dest='target_platform',
                      default = None,
                      choices = ['linux', 'darwin', 'win32', 'armv6-darwin'],
                      help = 'Target platform')

    parser.add_option('--skip-tests', dest='skip_tests',
                      action = 'store_true',
                      default = False,
                      help = 'Skip unit-tests. Default is false')

    parser.add_option('--skip-codesign', dest='skip_codesign',
                      action = 'store_true',
                      default = False,
                      help = 'skip code signing. Default is false')

    parser.add_option('--no-colors', dest='no_colors',
                      action = 'store_true',
                      default = False,
                      help = 'No color output. Default is color output')

    parser.add_option('--archive-path', dest='archive_path',
                      default = None,
                      help = 'Archive build. Set ssh-path, host:path, to archive build to')

    parser.add_option('--set-version', dest='set_version',
                      default = None,
                      help = 'Set version explicitily when bumping version')

    options, args = parser.parse_args()

    if len(args) == 0:
        parser.error('No command specified')

    c = Configuration(dynamo_home = os.environ.get('DYNAMO_HOME', None),
                      target_platform = options.target_platform,
                      eclipse_home = options.eclipse_home,
                      skip_tests = options.skip_tests,
                      skip_codesign = options.skip_codesign,
                      no_colors = options.no_colors,
                      archive_path = options.archive_path,
                      set_version = options.set_version)

    for cmd in args:
        f = getattr(c, cmd, None)
        if not f:
            parser.error('Unknown command %s' % cmd)
        f()
