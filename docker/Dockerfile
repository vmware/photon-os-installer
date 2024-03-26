# to debug poi:
# docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer .

# to use a mirror:
# sudo docker buildx build -t photon/installer --build-arg DOCKER_PROXY=harbor-repo.vmware.com/dockerhub-proxy-cache/ .

# Example run:
# sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-image -c sample_ks.yaml -v 4.0

# stage to clone poi
ARG DOCKER_PROXY
ARG TDNF_OPTIONS
FROM ${DOCKER_PROXY}library/photon:5.0 AS builder

RUN tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y update && \
    tdnf ${TDNF_OPTIONS} -y install \
    git && \
    rm -rf /var/cache/tdnf

RUN cd / && git clone https://github.com/vmware/photon-os-installer.git


# this stage is a place holder that can be overidden with the
# --build-context arg
FROM scratch AS poi-helper
COPY --from=builder /photon-os-installer /


# this stage builds an RPM from photon-os-installer which can
# be installed into the final image and into the initrd
ARG DOCKER_PROXY
FROM ${DOCKER_PROXY}library/photon:5.0 as poi-rpm-builder
ARG TDNF_OPTIONS

RUN tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y install git rpm-build python3

COPY --from=poi-helper / /photon-os-installer

COPY build-rpms.sh /usr/bin/

RUN cd /photon-os-installer && build-rpms.sh photon-os-installer


# final image
ARG DOCKER_PROXY
FROM ${DOCKER_PROXY}library/photon:5.0
ARG TDNF_OPTIONS
ARG TARGETARCH

RUN tdnf ${TDNF_OPTIONS} makecache && \
    tdnf ${TDNF_OPTIONS} -y update && \
    tdnf ${TDNF_OPTIONS} -y install \
    zlib tar \
    util-linux coreutils findutils binutils cdrkit \
    gptfdisk grub2 \
    e2fsprogs btrfs-progs xfsprogs kpartx lvm2 dosfstools \
    createrepo rpm jq jc \
    python3-PyYAML \
    python3-rpm \
    qemu-img \
    open-vmdk ostree rpm-ostree \
    stig-hardening \
    $([ "${TARGETARCH}" == "amd64" ] && echo grub2-pc) && \
    rm -rf /var/cache/tdnf

COPY --from=poi-rpm-builder /usr/src/photon /poi
RUN createrepo /poi

# install directly from path to make sure we are using current source
RUN tdnf ${TDNF_OPTIONS} -y install /poi/RPMS/*/photon-os-installer-*.rpm

COPY create-image \
     create-ova \
     create-repo \
     create-azure \
     create-ostree \
     poi-pkglist yjson \
     /usr/bin

VOLUME /repo /workdir

# ansible needs this
ENV LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 LANGUAGE=en_US.UTF-8

WORKDIR /workdir
