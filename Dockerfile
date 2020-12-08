FROM apertium/base
LABEL maintainer hanspeter@nynodata.no
WORKDIR /root

# Install packaged dependencies

RUN apt-get -qq update && apt-get -qq install \
    apt-utils \
    automake \
    gcc-multilib \
    git \
    python \
    python3-dev \
    python3-pip \
    sqlite3 \
    zlib1g-dev

# Install CLD2

RUN git clone https://github.com/CLD2Owners/cld2
RUN cd /root/cld2/internal && \
    CPPFLAGS='-std=c++98' ./compile_libs.sh && \
    cp *.so /usr/lib/
RUN git clone https://github.com/mikemccand/chromium-compact-language-detector
RUN cd /root/chromium-compact-language-detector && \
    python3 setup.py build && python3 setup_full.py build && \
    python3 setup.py install && python3 setup_full.py install

# Install Apertium-related libraries (and a test pair)

RUN apt-get -qq update && apt-get -qq install giella-core giella-shared hfst-ospell
RUN apt-get -qq update && apt-get -qq install apertium-nno-nob
RUN apt-get -qq update && apt-get -qq install apertium-nob
RUN apt-get -qq update && apt-get -qq install apertium-nno

# Install APy

COPY Pipfile apertium-apy/
COPY Pipfile.lock apertium-apy/
RUN pip3 install pipenv
RUN cd apertium-apy && pipenv install --deploy --system

COPY . apertium-apy
RUN cd apertium-apy && make -j2

# Run APy

EXPOSE 2737
ENTRYPOINT ["python3", "/root/apertium-apy/servlet.py", "--lang-names", "/root/apertium-apy/langNames.db"]
CMD ["/usr/share/apertium/modes", "--port", "2737"]
