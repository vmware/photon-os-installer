# to debug poi:
# docker buildx build --build-context poi-helper=/home/okurth/projects/photon-os-installer .

# Example run:
# sudo docker run -ti --rm --privileged -v/dev:/dev -v$(pwd):/workdir -v /home/okurth/poi/repo/:/repo poi-debug create-image -c sample_ks.yaml -v 4.0

FROM photon:5.0 AS builder
ARG TARGETARCH

RUN tdnf makecache
RUN tdnf -y update
RUN tdnf -y install \
    python3 python3-pip build-essential zlib-devel \
    git curl tar

RUN cd / && git clone https://github.com/vmware/photon-os-installer.git

RUN cd / && git clone https://github.com/vmware/open-vmdk.git
RUN cd /open-vmdk && make && make install DESTDIR=/installroot

RUN curl -LO https://github.com/mikefarah/yq/releases/download/v4.34.1/yq_linux_${TARGETARCH}.tar.gz && \
    tar zxf yq_linux_${TARGETARCH}.tar.gz


FROM scratch AS poi-helper
COPY --from=builder /photon-os-installer /


FROM photon:5.0
ARG TARGETARCH

RUN tdnf makecache
RUN tdnf -y update
RUN tdnf -y install \
    zlib tar \
    util-linux coreutils findutils binutils cdrkit \
    gptfdisk grub2 \
    e2fsprogs kpartx lvm2 dosfstools \
    createrepo rpm jq \
    python3 python3-pip python3-setuptools python3-curses \
    python3-pyYAML python3-lxml python3-cracklib \
    $([ "${TARGETARCH}" == "amd64" && grub2-pc ])

COPY --from=poi-helper / /photon-os-installer
RUN cd /photon-os-installer && pip3 install . # && cd .. && rm -rf /photon-os-installer

COPY --from=builder /installroot /
COPY --from=builder yq_linux_${TARGETARCH} /usr/bin/yq
COPY create-image /usr/bin
COPY create-ova /usr/bin
COPY create-repo /usr/bin
COPY poi-pkglist /usr/bin

VOLUME /repo /workdir

WORKDIR /workdir
