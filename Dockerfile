FROM debian:jessie-slim
LABEL maintainer sushain@skc.name
WORKDIR /root

# Install packaged dependencies

RUN apt-get -qq update && apt-get -qq install \
    apt-utils \
    automake \
    build-essential \
    gawk \
    gcc-multilib \
    git \
    locales \
    libtool \
    pkg-config \
    python \
    python3-dev \
    python3-pip \
    subversion \
    sqlite3 \
    wget \
    zlib1g-dev

# Repair locales

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

# Install CLD2

RUN git clone https://github.com/CLD2Owners/cld2
RUN cd /root/cld2/internal && \
    ./compile_libs.sh && cp *.so /usr/lib/
RUN git clone https://github.com/mikemccand/chromium-compact-language-detector
RUN cd /root/chromium-compact-language-detector && \
    python3 setup.py build && python3 setup_full.py build && \
    python3 setup.py install && python3 setup_full.py install

# Install Apertium and related libraries

ADD https://apertium.projectjj.com/apt/install-nightly.sh .
RUN bash install-nightly.sh
RUN apt-get -qq update && apt-get -qq install apertium-all-dev
RUN apt-get -qq update && apt-get -qq install giella-core giella-shared hfst-ospell
RUN apt-get -qq update && apt-get -qq install apertium-en-es

# Install APy

COPY . apertium-apy
RUN pip3 install -r apertium-apy/requirements.txt
RUN cd apertium-apy && make -j2

# Run APy

EXPOSE 2737
ENTRYPOINT ["python3", "/root/apertium-apy/servlet.py", "--lang-names", "/root/apertium-apy/langNames.db"]
CMD ["/usr/share/apertium/modes", "--port", "2737"]
