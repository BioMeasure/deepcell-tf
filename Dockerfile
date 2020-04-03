# Use tensorflow/tensorflow as the base image
# Change the build arg to edit the tensorflow version.
# Only supporting python3.
ARG TF_VERSION=1.15.0-gpu

FROM tensorflow/tensorflow:${TF_VERSION}-py3

# System maintenance
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-tk \
    git \
    libsm6 && \
    rm -rf /var/lib/apt/lists/* && \
    /usr/local/bin/pip install --upgrade pip

# Copy the setup.py and requirements.txt and install the deepcell-tf dependencies
COPY setup.py requirements.txt /opt/deepcell-tf/

# Prevent reinstallation of tensorflow and install all other requirements.
RUN sed -i "/tensorflow/d" /opt/deepcell-tf/requirements.txt && \
    pip install -r /opt/deepcell-tf/requirements.txt

# Copy the rest of the package code and its scripts
COPY deepcell /opt/deepcell-tf/deepcell

# Install deepcell via setup.py
RUN pip install /opt/deepcell-tf && \
    cd /opt/deepcell-tf && \
    python setup.py build_ext --inplace

# Install the latest version of keras-applications
RUN pip install --upgrade git+https://github.com/keras-team/keras-applications.git

# Install edge tpu compiler
RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -

RUN echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | tee   /etc/apt/sources.list.d/coral-edgetpu.list

RUN apt-get update

# RUN apt-get install -y edgetpu

RUN apt-get install -y libedgetpu1-std

RUN mkdir /coral 

WORKDIR /coral

RUN git clone https://github.com/google-coral/tflite.git

RUN pip install https://dl.google.com/coral/python/tflite_runtime-2.1.0.post1-cp36-cp36m-linux_x86_64.whl

WORKDIR /coral/tflite/python/examples/classification

RUN ./install_requirements.sh

WORKDIR /notebooks

# Older versions of TensorFlow have notebooks, but they may not exist
RUN if [ -n "$(find /notebooks/ -prune)" ] ; then \
      mkdir -p /notebooks/intro_to_tensorflow && \
      ls -d /notebooks/* | grep -v intro_to_tensorflow | \
      xargs -r mv -t /notebooks/intro_to_tensorflow ; \
    fi

# Copy over deepcell notebooks
COPY scripts/ /notebooks/

CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--allow-root"]
