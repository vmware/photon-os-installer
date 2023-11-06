#!/bin/bash

PACKAGE=$1

SPEC=${PACKAGE}.spec
VERSION=$(rpmspec -q --srpm --queryformat "[%{VERSION}\n]" ${SPEC})
FULLNAME=${PACKAGE}-${VERSION}
BUILD_REQUIRES=$(rpmspec -q --buildrequires ${SPEC})
TARBALL=$(rpmspec -q --srpm --queryformat "[%{SOURCE}\n]" ${SPEC})
ARCH=$(uname -m)
RPM_BUILD_DIR="/usr/src/photon"
DIST=.ph5

# https://github.com/actions/checkout/issues/760
git config --global --add safe.directory $(pwd)

tar zcf ${TARBALL} --transform "s,^,${FULLNAME}/," $(git ls-files)

tdnf install -y ${BUILD_REQUIRES}

mkdir -p ${RPM_BUILD_DIR}
mkdir -p ${RPM_BUILD_DIR}/{SOURCES,BUILD,RPMS,SRPMS}
mv ${TARBALL} ${RPM_BUILD_DIR}/SOURCES/

rpmbuild --nodeps -D "dist ${DIST}" -D "_topdir ${RPM_BUILD_DIR}" -ba ${SPEC}
