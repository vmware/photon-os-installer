# to debug poi:
# docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer .

# to use a mirror:
# sudo docker buildx build -t photon/installer --build-arg DOCKER_PROXY=harbor-repo.vmware.com/dockerhub-proxy-cache/ .

# Example run:
# sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-image -c sample_ks.yaml -v 4.0

# base stage
ARG DOCKER_PROXY
FROM ${DOCKER_PROXY}library/photon:5.0 AS base

# SNAPSHOT_BASEURL: where the snapshot's repodata lives. Override with
#   --build-arg SNAPSHOT_BASEURL=http://internal-mirror/photon/...
# for airgapped or alternate-mirror builds. Default is the canonical
# Broadcom Photon 5.0 main repo (which carries repodata).
# SNAPSHOT_LISTURL: optional snapshot=URL pinning (TDNF on Photon 5.0
# honors this); empty leaves the repo unpinned.
ARG SNAPSHOT_BASEURL=https://packages.broadcom.com/photon/5.0/photon_5.0_x86_64
ARG SNAPSHOT_LISTURL=

RUN set -eu; \
    if [ ! -f /etc/yum.repos.d/photon-snapshot.repo ]; then \
        { \
            echo '[photon-snapshot]'; \
            echo 'name=VMware Photon Linux $releasever ($basearch) Snapshot for Updates'; \
            echo "baseurl=${SNAPSHOT_BASEURL}"; \
            [ -n "${SNAPSHOT_LISTURL}" ] && echo "snapshot=${SNAPSHOT_LISTURL}"; \
            echo 'gpgkey=file:///etc/pki/rpm-gpg/VMWARE-RPM-GPG-KEY file:///etc/pki/rpm-gpg/VMWARE-RPM-GPG-KEY-4096'; \
            echo 'gpgcheck=1'; \
            echo 'enabled=1'; \
            echo 'skip_if_unavailable=1'; \
            echo 'skip_md_filelists=1'; \
        } > /etc/yum.repos.d/photon-snapshot.repo; \
    fi && \
    tdnf-config edit photon-snapshot enabled=1 && \
    tdnf-config edit photon-updates enabled=0

# stage to clone poi
ARG DOCKER_PROXY
ARG TDNF_OPTIONS
FROM base AS builder

RUN echo '%__transaction_unshare %{nil}' >> /etc/rpm/macros.unshare && \
    tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y update && \
    tdnf ${TDNF_OPTIONS} -y install \
    git && \
    rm -rf /var/cache/tdnf

RUN cd / && git clone --depth 1 https://github.com/vmware/photon-os-installer.git


# this stage is a place holder that can be overidden with the
# --build-context arg
FROM scratch AS poi-helper
COPY --from=builder /photon-os-installer /


# this stage builds an RPM from photon-os-installer which can
# be installed into the final image and into the initrd
ARG DOCKER_PROXY
FROM base AS poi-rpm-builder
ARG TDNF_OPTIONS

RUN echo '%__transaction_unshare %{nil}' >> /etc/rpm/macros.unshare && \
    tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y install git rpm-build python3 createrepo

COPY --from=poi-helper / /photon-os-installer

COPY build-rpms.sh /usr/bin/

RUN cd /photon-os-installer && build-rpms.sh photon-os-installer


# final image
ARG DOCKER_PROXY
FROM base
ARG TDNF_OPTIONS
ARG TARGETARCH

RUN echo '%__transaction_unshare %{nil}' >> /etc/rpm/macros.unshare && \
    tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y remove toybox && \
    tdnf ${TDNF_OPTIONS} -y update && \
    tdnf ${TDNF_OPTIONS} -y install \
    zlib tar \
    gzip cpio \
    util-linux coreutils findutils gawk binutils cdrkit \
    gptfdisk grub2 \
    e2fsprogs btrfs-progs xfsprogs kpartx lvm2 dosfstools \
    createrepo rpm jq jc \
    python3-PyYAML \
    python3-rpm \
    qemu-img \
    open-vmdk \
    stig-hardening \
    mkpasswd \
    $([ "${TARGETARCH}" == "amd64" ] && echo grub2-pc) && \
    rm -rf /var/cache/tdnf

COPY --from=poi-rpm-builder /usr/src/photon /poi
RUN createrepo /poi

# install directly from path to make sure we are using current source
RUN tdnf ${TDNF_OPTIONS} -y --nogpgcheck install /poi/RPMS/*/photon-os-installer-*.rpm

COPY \
     create-image \
     create-ova \
     create-repo \
     create-azure \
     create-cherrypicks-repo \
     create-pkg \
     poi-pkglist yjson \
     /usr/bin

VOLUME /repo /workdir

# ansible needs this
ENV LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 LANGUAGE=en_US.UTF-8

WORKDIR /workdir
