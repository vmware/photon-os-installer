# to debug poi:
# docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer .

# to use a mirror:
# sudo docker buildx build -t photon/installer --build-arg DOCKER_PROXY=harbor-repo.vmware.com/dockerhub-proxy-cache/ .

# Example run:
# sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-image -c sample_ks.yaml -v 4.0

ARG DOCKER_PROXY
FROM ${DOCKER_PROXY}library/photon:5.0 AS builder

ARG TARGETARCH

RUN tdnf makecache && \
    tdnf -y update && \
    tdnf -y install \
    git && \
    rm -rf /var/cache/tdnf

RUN cd / && git clone https://github.com/vmware/photon-os-installer.git


FROM scratch AS poi-helper
COPY --from=builder /photon-os-installer /


ARG DOCKER_PROXY
FROM ${DOCKER_PROXY}library/photon:5.0

ARG TARGETARCH

RUN tdnf makecache && \
    tdnf -y update && \
    tdnf -y install \
    zlib tar \
    util-linux coreutils findutils binutils cdrkit \
    gptfdisk grub2 \
    e2fsprogs kpartx lvm2 dosfstools \
    createrepo rpm jq \
    python3 python3-pip python3-setuptools python3-curses \
    python3-pyYAML python3-lxml python3-cracklib qemu-img \
    open-vmdk \
    $([ "${TARGETARCH}" == "amd64" ] && echo grub2-pc) && \
    rm -rf /var/cache/tdnf

COPY --from=poi-helper / /photon-os-installer
RUN cd /photon-os-installer && pip3 install . # && cd .. && rm -rf /photon-os-installer

COPY create-image create-ova create-repo create-azure \
     poi-pkglist yjson \
     /usr/bin

VOLUME /repo /workdir

WORKDIR /workdir
