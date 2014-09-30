# NOTE: This script is only used for CI
# The corresponding file for development is build.xml

set -e
mkdir -p lib/linux
mkdir -p lib/x86_64-darwin
mkdir -p lib/win32

SHA1=`git log --pretty=%H -n1`

cp -v $DYNAMO_HOME/archive/${SHA1}/engine/linux/libtexc_shared.so lib/linux/libtexc_shared.so
cp -v $DYNAMO_HOME/archive/${SHA1}/engine/x86_64-darwin/libtexc_shared.dylib lib/x86_64-darwin/libtexc_shared.dylib
cp -v $DYNAMO_HOME/archive/${SHA1}/engine/win32/texc_shared.dll lib/win32/texc_shared.dll
