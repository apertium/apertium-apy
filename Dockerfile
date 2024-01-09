FROM ghcr.io/apertium/base
LABEL maintainer sushain@skc.name

# Install packaged dependencies

RUN apt-get -qq update && apt-get -qqfy dist-upgrade && apt-get -qqfy install python3 python3-dev python3-setuptools python3-tornado python3-streamparser python3-requests python3-chardet python3-commentjson python3-lxml libcld2-dev

# Install CLD2

WORKDIR /root/tmp
ADD https://github.com/mikemccand/chromium-compact-language-detector/archive/refs/heads/master.zip chromium-compact-language-detector.zip
RUN export CPPFLAGS="-I/usr/include/cld2/public -I/usr/include/cld2/internal" && \
    unzip -q chromium-compact-language-detector.zip && \
    cd chromium-compact-language-detector-master && \
    python3 setup.py build && python3 setup_full.py build && \
    python3 setup.py install && python3 setup_full.py install
WORKDIR /root
RUN rm -rf /root/tmp

# Install Apertium-related libraries (and a test pair)

RUN apt-get -qq update && apt-get -qq install \
    giella-core \
    hfst-ospell \
    apertium-eng-spa

# Install APy
COPY . apertium-apy
RUN cd apertium-apy && make -j4

# Run APy

EXPOSE 2737
ENTRYPOINT ["python3", "/root/apertium-apy/servlet.py", "--lang-names", "/root/apertium-apy/langNames.db"]
CMD ["/usr/share/apertium/modes", "--port", "2737"]
