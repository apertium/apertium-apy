FROM ghcr.io/apertium/base
LABEL maintainer sushain@skc.name

# Install packaged dependencies

RUN apt-get -qq update && apt-get -qq install python3-pip

# Install CLD2

WORKDIR /root/tmp
ADD https://github.com/CLD2Owners/cld2/archive/refs/heads/master.zip cld2.zip
RUN unzip -q cld2.zip && \
    mv cld2-master cld2 && \
    cd cld2/internal && \
    CPPFLAGS='-std=c++98' ./compile_libs.sh && \
    cp *.so /usr/lib/
ADD https://github.com/mikemccand/chromium-compact-language-detector/archive/refs/heads/master.zip chromium-compact-language-detector.zip
RUN unzip -q chromium-compact-language-detector.zip && \
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

COPY Pipfile apertium-apy/
COPY Pipfile.lock apertium-apy/
RUN pip3 install pipenv
RUN cd apertium-apy && pipenv install --deploy --system

COPY . apertium-apy
RUN cd apertium-apy && make -j4

# Run APy

EXPOSE 2737
ENTRYPOINT ["python3", "/root/apertium-apy/servlet.py", "--lang-names", "/root/apertium-apy/langNames.db"]
CMD ["/usr/share/apertium/modes", "--port", "2737"]
