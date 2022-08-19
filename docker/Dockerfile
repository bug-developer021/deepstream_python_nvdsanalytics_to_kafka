FROM nvcr.io/nvidia/deepstream:6.1-triton

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

RUN mv /etc/apt/sources.list /etc/apt/sources.list.bak
COPY docker/sources.list /etc/apt/sources.list

RUN apt-get update
# Install required dependencies
RUN apt-get install -yq --no-install-recommends \
    # ffmpeg \
    python3-gst-1.0 \
    python3-gi \
    python-gi-dev \
    python3-opencv \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*




RUN cd /opt/nvidia/deepstream/deepstream/sources \
    && git clone https://github.com/NVIDIA-AI-IOT/deepstream_python_apps.git 



COPY src/deepstream-sources/includes/nvdsmeta_schema.h /opt/nvidia/deepstream/deepstream/sources/includes/nvdsmeta_schema.h
COPY src/deepstream-sources/libs/nvmsgconv /opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv
# for build python bindings
COPY src/deepstream-python-bindings/bindschema.cpp /opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps/bindings/src/bindschema.cpp

# rebuild custom payload for sending messages to kafka
RUN cd /opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv \
    && make \
    && cp libnvds_msgconv.so /opt/nvidia/deepstream/deepstream/lib/libnvds_msgconv.so


# build python bindings
RUN cd /opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps \
    && git submodule update --init \
    && cd ./3rdparty/gst-python \
    && ./autogen.sh \
    && make \
    && make install \
    && cd ../../bindings \
    && mkdir build \
    && cd build \
    && cmake ..  -DPYTHON_MAJOR_VERSION=3 -DPYTHON_MINOR_VERSION=8 \
    && make \
    && pip3 install ./pyds-*-py3-none*.whl


WORKDIR /opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps
RUN pip3 install jupyter jupyterlab

CMD jupyter-notebook  --notebook-dir=/opt/nvidia/deepstream/deepstream-6.1 --ip=0.0.0.0 --no-browser --allow-root --port=8888 --NotebookApp.token='' 