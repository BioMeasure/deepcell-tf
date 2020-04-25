# Copyright 2016-2019 The Van Valen Lab at the California Institute of
# Technology (Caltech), with support from the Paul Allen Family Foundation,
# Google, & National Institutes of Health (NIH) under Grant U24CA224309-01.
# All rights reserved.
#
# Licensed under a modified Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.github.com/vanvalenlab/deepcell-tf/LICENSE
#
# The Work provided may be used for non-commercial academic purposes only.
# For any other use of the Work, including commercial use, please contact:
# vanvalenlab@gmail.com
#
# Neither the name of Caltech nor the names of its contributors may be used
# to endorse or promote products derived from this software without specific
# prior written permission.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Feature pyramid network utility functions"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

import re

from tensorflow.python.keras import backend as K
from tensorflow.python.keras.models import Model
<<<<<<< HEAD
from tensorflow.python.keras.layers import Conv2D, Conv3D, DepthwiseConv2D, TimeDistributed, ConvLSTM2D
from tensorflow.python.keras.layers import Input, Concatenate, Add
from tensorflow.python.keras.layers import Permute, Reshape
from tensorflow.python.keras.layers import Activation, Lambda, BatchNormalization, Softmax
from tensorflow.python.keras.initializers import RandomNormal
from tensorflow.python.keras.layers import UpSampling2D, UpSampling3D

from deepcell.initializers import PriorProbability
from deepcell.layers import TensorProduct, ConvGRU2D
from deepcell.layers import FilterDetections
from deepcell.layers import ImageNormalization2D, Location2D
from deepcell.layers import Anchors, RegressBoxes, ClipBoxes
from deepcell.layers import UpsampleLike
from deepcell.utils.retinanet_anchor_utils import AnchorParameters

from deepcell.utils.backbone_utils import get_backbone
from deepcell.utils.misc_utils import get_sorted_keys

def __merge_temporal_features(feature, mode='conv', feature_size=256, frames_per_batch=1):
    if mode == 'conv':
        x = Conv3D(feature_size, 
                    (frames_per_batch, 3, 3), 
                    strides=(1,1,1),
                    padding='same',
                    )(feature)
        x = BatchNormalization(axis=-1)(x)
        x = Activation('relu')(x)
    elif mode == 'lstm':
        x = ConvLSTM2D(feature_size, 
                       (3, 3), 
                        padding='same',
                        activation='relu',
                        return_sequences=True)(feature)
    elif mode == 'gru':
        x = ConvGRU2D(feature_size,
                        (3, 3),
                        padding='same',
                        activation='relu',
                        return_sequences=True)(feature)

    temporal_feature = x     

    return temporal_feature

def create_pyramid_level(backbone_input,
                         upsamplelike_input=None,
                         addition_input=None,
                         level=5,
                         ndim=2,
                         lite=False,
                         feature_size=256):
    """Create a pyramid layer from a particular backbone input layer.

    Args:
        backbone_input (layer): Backbone layer to use to create they pyramid layer
        upsamplelike_input ([type], optional): Defaults to None. Input to use
            as a template for shape to upsample to
        addition_input (layer, optional): Defaults to None. Layer to add to
            pyramid layer after conv and upsample
        level (int, optional): Defaults to 5. Level to use in layer names
        feature_size (int, optional): Defaults to 256. Number of filters for
            convolutional layer
        ndim (int): The spatial dimensions of the input data. Default is 2,
            but it also works with 3

    Returns:
        tuple: Pyramid layer after processing, upsampled pyramid layer

    Raises:
        ValueError: ndim is not 2 or 3
    """

    acceptable_ndims = {2, 3}
    if ndim not in acceptable_ndims:
        raise ValueError('Only 2 and 3 dimensional networks are supported')

    if ndim==3 and lite:
        raise ValueError('lite mode does not currently work with 3 dimensional networks')

    upsampling = UpSampling2D if ndim == 2 else UpSampling3D
    size = (2,2) if ndim == 2 else (1,2,2)

    reduced_name = 'C{}_reduced'.format(level)
    upsample_name = 'P{}_upsampled'.format(level)
    addition_name = 'P{}_merged'.format(level)
    final_name = 'P{}'.format(level)

    # Apply 1x1 conv to backbone layer
    if ndim == 2:
        pyramid = Conv2D(feature_size, (1, 1), strides=(1, 1),
                         padding='same', name=reduced_name)(backbone_input)
    else:
        pyramid = Conv3D(feature_size, (1, 1, 1), strides=(1, 1, 1),
                         padding='same', name=reduced_name)(backbone_input)

    # Add and then 3x3 conv
    if addition_input is not None:
        pyramid = Add(name=addition_name)([pyramid, addition_input])

    # Upsample pyramid input
    if upsamplelike_input is not None:
        # Pyramid construction only works for image sizes that
        # are powers of two 
        pyramid_upsample = upsampling(size=size, name=upsample_name, interpolation='bilinear')(pyramid)
    else:
        pyramid_upsample = None

    if ndim == 2:
        if lite:
            pyramid_final = DepthwiseConv2D((3,3), strides=(1,1), 
                                padding='same', name=final_name)(pyramid)
        else:
            pyramid_final = Conv2D(feature_size, (3, 3), strides=(1, 1),
                               padding='same', name=final_name)(pyramid)
    else:
        pyramid_final = Conv3D(feature_size, (1, 3, 3), strides=(1, 1, 1),
                               padding='same', name=final_name)(pyramid)

    return pyramid_final, pyramid_upsample


def __create_pyramid_features(backbone_dict, ndim=2, 
                              feature_size=256,
                              lite=False,
                              include_final_layers=True):
    """Creates the FPN layers on top of the backbone features.

    Args:
        backbone_dict (dictionary): A dictionary of the backbone layers, with
            the names as keys, e.g. {'C0': C0, 'C1': C1, 'C2': C2, ...}
        feature_size (int, optional): Defaults to 256. The feature size to use
            for the resulting feature levels.
        include_final_layers (bool): Add two coarser pyramid levels
        ndim (int): The spatial dimensions of the input data.
            Default is 2, but it also works with 3

    Returns:
        dict: The feature pyramid names and levels,
            e.g. {'P3': P3, 'P4': P4, ...}
            Each backbone layer gets a pyramid level, and two additional levels
            are added, e.g. [C3, C4, C5] --> [P3, P4, P5, P6, P7]

    Raises:
        ValueError: ndim is not 2 or 3
    """

=======
from tensorflow.python.keras.layers import Conv2D, Conv3D
from tensorflow.python.keras.layers import TimeDistributed, ConvLSTM2D
from tensorflow.python.keras.layers import Input, Concatenate
from tensorflow.python.keras.layers import Activation, BatchNormalization, Softmax
from tensorflow.python.keras.layers import UpSampling2D, UpSampling3D

from deepcell.layers import ConvGRU2D
from deepcell.layers import ImageNormalization2D, Location2D
from deepcell.model_zoo.fpn import __create_pyramid_features
from deepcell.utils.backbone_utils import get_backbone
from deepcell.utils.misc_utils import get_sorted_keys


def __merge_temporal_features(feature, mode='conv', feature_size=256,
                              frames_per_batch=1):
    """ Merges feature with its temporal residual through addition.
    Input feature (x) --> Temporal convolution* --> Residual feature (x')
    *Type of temporal convolution specified by "mode" argument
    Output: y = x + x'

    Args:
        feature: Input layer
        mode (str, optional): Mode of temporal convolution. Choose from
            {'conv','lstm','gru', None}. Defaults to 'conv'.
        feature_size (int, optional): Defaults to 256.
        frames_per_batch (int, optional): Defaults to 1.

    Raises:
        ValueError: Mode not 'conv', 'lstm', 'gru' or None

    Returns:
        Input feature merged with its residual from a temporal convolution.
            If mode=None, the output is exactly the input.
    """
    # Check inputs to mode
    acceptable_modes = {'conv', 'lstm', 'gru', None}
    if mode is not None:
        mode = str(mode).lower()
        if mode not in acceptable_modes:
            raise ValueError('Mode {} not supported. Please choose '
                             'from {}.'.format(mode, str(acceptable_modes)))

    if mode == 'conv':
        x = Conv3D(feature_size,
                   (frames_per_batch, 3, 3),
                   strides=(1, 1, 1),
                   padding='same',
                   )(feature)
        x = BatchNormalization(axis=-1)(x)
        x = Activation('relu')(x)
    elif mode == 'lstm':
        x = ConvLSTM2D(feature_size,
                       (3, 3),
                       padding='same',
                       activation='relu',
                       return_sequences=True)(feature)
    elif mode == 'gru':
        x = ConvGRU2D(feature_size,
                      (3, 3),
                      padding='same',
                      activation='relu',
                      return_sequences=True)(feature)
    else:
        x = feature

    temporal_feature = x

    return temporal_feature


def semantic_upsample(x, n_upsample, n_filters=64, ndim=2,
                      semantic_id=0, interpolation='bilinear'):
    """Performs iterative rounds of 2x upsampling and
    convolutions with a 3x3 filter to remove aliasing effects

    Args:
        x (tensor): The input tensor to be upsampled
        n_upsample (int): The number of 2x upsamplings
        n_filters (int, optional): Defaults to 64. The number of filters for
            the 3x3 convolution
        ndim (int): The spatial dimensions of the input data.
            Default is 2, but it also works with 3
        interpolation (str): Choice of interpolation mode for upsampling
            layers from ['bilinear', 'nearest']. Defaults to bilinear.

    Raises:
        ValueError: ndim is not 2 or 3

    Returns:
        tensor: The upsampled tensor
    """
    # Check input to ndims
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    acceptable_ndims = [2, 3]
    if ndim not in acceptable_ndims:
        raise ValueError('Only 2 and 3 dimensional networks are supported')

<<<<<<< HEAD
    # Get names of the backbone levels and place in ascending order
    backbone_names = get_sorted_keys(backbone_dict)
    backbone_features = [backbone_dict[name] for name in backbone_names]

    pyramid_names = []
    pyramid_finals = []
    pyramid_upsamples = []

    # Reverse lists
    backbone_names.reverse()
    backbone_features.reverse()

    for i in range(len(backbone_names)):

        N = backbone_names[i]
        level = int(re.findall(r'\d+', N)[0])
        p_name = 'P{}'.format(level)
        pyramid_names.append(p_name)

        backbone_input = backbone_features[i]

        # Don't add for the bottom of the pyramid
        if i == 0:
            if len(backbone_features) > 1:
                upsamplelike_input = backbone_features[i + 1]
            else:
                upsamplelike_input = None
            addition_input = None

        # Don't upsample for the top of the pyramid
        elif i == len(backbone_names) - 1:
            upsamplelike_input = None
            addition_input = pyramid_upsamples[-1]

        # Otherwise, add and upsample
        else:
            upsamplelike_input = backbone_features[i + 1]
            addition_input = pyramid_upsamples[-1]

        pf, pu = create_pyramid_level(backbone_input,
                                      upsamplelike_input=upsamplelike_input,
                                      addition_input=addition_input,
                                      level=level,
                                      lite=lite,
                                      ndim=ndim)
        pyramid_finals.append(pf)
        pyramid_upsamples.append(pu)

    # Add the final two pyramid layers
    if include_final_layers:
        # "Second to last pyramid layer is obtained via a
        # 3x3 stride-2 conv on the coarsest backbone"
        N = backbone_names[0]
        F = backbone_features[0]
        level = int(re.findall(r'\d+', N)[0]) + 1
        P_minus_2_name = 'P{}'.format(level)

        if ndim == 2:
            P_minus_2 = Conv2D(feature_size, kernel_size=(3, 3), strides=(2, 2),
                               padding='same', name=P_minus_2_name)(F)
        else:
            P_minus_2 = Conv3D(feature_size, kernel_size=(1, 3, 3),
                               strides=(1, 2, 2), padding='same',
                               name=P_minus_2_name)(F)

        pyramid_names.insert(0, P_minus_2_name)
        pyramid_finals.insert(0, P_minus_2)

        # "Last pyramid layer is computed by applying ReLU
        # followed by a 3x3 stride-2 conv on second to last layer"
        level = int(re.findall(r'\d+', N)[0]) + 2
        P_minus_1_name = 'P{}'.format(level)
        P_minus_1 = Activation('relu', name=N + '_relu')(P_minus_2)

        if ndim == 2:
            P_minus_1 = Conv2D(feature_size, kernel_size=(3, 3), strides=(2, 2),
                               padding='same', name=P_minus_1_name)(P_minus_1)
        else:
            P_minus_1 = Conv3D(feature_size, kernel_size=(1, 3, 3),
                               strides=(1, 2, 2), padding='same',
                               name=P_minus_1_name)(P_minus_1)

        pyramid_names.insert(0, P_minus_1_name)
        pyramid_finals.insert(0, P_minus_1)

    pyramid_names.reverse()
    pyramid_finals.reverse()

    # Reverse lists
    backbone_names.reverse()
    backbone_features.reverse()

    pyramid_dict = {}
    for name, feature in zip(pyramid_names, pyramid_finals):
        pyramid_dict[name] = feature

    return pyramid_dict

def semantic_upsample(x, n_upsample, n_filters=64, ndim=3, semantic_id=0):
    conv = Conv2D if ndim == 2 else Conv3D
    conv_kernel = (3,3) if ndim == 2 else (1,3,3)
    upsampling = UpSampling2D if ndim == 2 else UpSampling3D
    size = (2,2) if ndim == 2 else (1,2,2)
=======
    # Check input to interpolation
    acceptable_interpolation = {'bilinear', 'nearest'}
    if interpolation not in acceptable_interpolation:
        raise ValueError('Interpolation mode not supported. Choose from '
                         '["bilinear", "nearest"]')

    conv = Conv2D if ndim == 2 else Conv3D
    conv_kernel = (3, 3) if ndim == 2 else (1, 3, 3)
    upsampling = UpSampling2D if ndim == 2 else UpSampling3D
    size = (2, 2) if ndim == 2 else (1, 2, 2)
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    if n_upsample > 0:
        for i in range(n_upsample):
            x = conv(n_filters, conv_kernel, strides=1,
                     padding='same', data_format='channels_last',
                     name='conv_{}_semantic_upsample_{}'.format(i, semantic_id))(x)
<<<<<<< HEAD
            x = upsampling(size=size, 
                            name='upsampling_{}_semantic_upsample_{}'.format(i, semantic_id),
                            interpolation='bilinear')(x)
=======
            x = upsampling(size=size,
                           name='upsampling_{}_semantic_upsample_{}'.format(i, semantic_id),
                           interpolation=interpolation)(x)
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    else:
        x = conv(n_filters, conv_kernel, strides=1,
                 padding='same', data_format='channels_last',
                 name='conv_final_semantic_upsample_{}'.format(semantic_id))(x)
    return x

<<<<<<< HEAD
def __create_semantic_head(pyramid_dict,
                            n_classes=3,
                            n_filters=64,
                            n_dense=128,
                            semantic_id=0,
                            ndim=3,
                            include_top=False,
                            target_level=2,
                            **kwargs):

    conv = Conv2D if ndim == 2 else Conv3D
    conv_kernel = (1,1) if ndim==2 else (1,1,1)
=======

def __create_semantic_head(pyramid_dict,
                           n_classes=3,
                           n_filters=64,
                           n_dense=128,
                           semantic_id=0,
                           ndim=2,
                           include_top=False,
                           target_level=2,
                           interpolation='bilinear',
                           **kwargs):
    """Creates a semantic head from a feature pyramid network.

    Args:
        pyramid_dict (dict): dict of pyramid names and features
        n_classes (int): Defaults to 3.  The number of classes to be predicted
        n_filters (int): Defaults to 64. The number of convolutional filters.
        n_dense (int): Defaults to 128. Number of dense filters.
        semantic_id (int): Defaults to 0.
        ndim (int): Defaults to 2, 3d supported.
        include_top (bool): Defaults to False.
        target_level (int, optional): Defaults to 2. The level we need to reach.
            Performs 2x upsampling until we're at the target level.
        interpolation (str): Choice of interpolation mode for upsampling
            layers from ['bilinear', 'nearest']. Defaults to bilinear.

    Raises:
        ValueError: ndim must be 2 or 3

    Returns:
        keras.layers.Layer: The semantic segmentation head
    """
    # Check input to ndims
    if ndim not in {2, 3}:
        raise(ValueError('ndim must be either 2 or 3. '
                         'Received ndim = {}'.format(ndim)))

    # Check input to interpolation
    acceptable_interpolation = {'bilinear', 'nearest'}
    if interpolation not in acceptable_interpolation:
        raise ValueError('Interpolation mode not supported. Choose from '
                         '["bilinear", "nearest"]')

    conv = Conv2D if ndim == 2 else Conv3D
    conv_kernel = (1,) * ndim

>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    if K.image_data_format() == 'channels_first':
        channel_axis = 1
    else:
        channel_axis = -1

    if n_classes == 1:
        include_top = False
<<<<<<< HEAD
        
=======

>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    # Get pyramid names and features into list form
    pyramid_names = get_sorted_keys(pyramid_dict)
    pyramid_features = [pyramid_dict[name] for name in pyramid_names]

    # Reverse pyramid names and features
    pyramid_names.reverse()
    pyramid_features.reverse()

<<<<<<< HEAD
    semantic_features = []
    semantic_names = []

    # for N, P in zip(pyramid_names, pyramid_features):

    #     # Get level and determine how much to upsample
    #     level = int(re.findall(r'\d+', N)[0])
    #     n_upsample = level - target_level

    #     # Use semantic upsample to get semantic map
    #     semantic_features.append(semantic_upsample_prototype(P, n_upsample, ndim=ndim))
    #     semantic_names.append('Q{}'.format(level))

    # # Add all the semantic layers
    # semantic_sum = Add()(semantic_features)

    semantic_sum = pyramid_features[-1]
    semantic_names = pyramid_names[-1]

    # Final upsampling
    min_level = int(re.findall(r'\d+', semantic_names[-1])[0])
    n_upsample = min_level
    x = semantic_upsample(semantic_sum, n_upsample, ndim=ndim, semantic_id=semantic_id)

    # First tensor product
    x = conv(n_dense, conv_kernel, strides=1, 
                padding='same', data_format='channels_last', 
                name='tensor_product_0_semantic_{}'.format(semantic_id))(x)

    # x = TensorProduct(n_dense, name='tensor_product_0_semantic_{}'.format(semantic_id))(x)
    x = BatchNormalization(axis=channel_axis, name='batch_normalization_0_semantic_{}'.format(semantic_id))(x)
    x = Activation('relu', name='relu_0_semantic_{}'.format(semantic_id))(x)

    # Apply tensor product and softmax layer
    x = conv(n_classes, conv_kernel, strides=1, 
                padding='same', data_format='channels_last', 
                name='tensor_product_1_semantic_{}'.format(semantic_id))(x)
    # x = TensorProduct(n_classes, name='tensor_product_1_semantic_{}'.format(semantic_id))(x)
=======
    semantic_feature = pyramid_features[-1]
    semantic_name = pyramid_names[-1]

    # Final upsampling
    min_level = int(re.findall(r'\d+', semantic_name[-1])[0])
    n_upsample = min_level
    x = semantic_upsample(semantic_feature, n_upsample, ndim=ndim,
                          interpolation=interpolation, semantic_id=semantic_id)

    # Apply conv in place of previous tensor product
    x = conv(n_dense, conv_kernel, strides=1,
             padding='same', data_format='channels_last',
             name='conv_0_semantic_{}'.format(semantic_id))(x)
    x = BatchNormalization(axis=channel_axis)(x)
    x = Activation('relu', name='relu_0_semantic_{}'.format(semantic_id))(x)

    # Apply conv and softmax layer
    x = conv(n_classes, conv_kernel, strides=1,
             padding='same', data_format='channels_last',
             name='conv_1_semantic_{}'.format(semantic_id))(x)
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e

    if include_top:
        x = Softmax(axis=channel_axis, name='semantic_{}'.format(semantic_id))(x)
    else:
        x = Activation('relu', name='semantic_{}'.format(semantic_id))(x)

    return x

<<<<<<< HEAD
def PanopticNet(backbone,
               input_shape,
               inputs=None,
               backbone_levels=['C3','C4','C5'],
               pyramid_levels=['P3','P4','P5','P6','P7'],
               create_pyramid_features=__create_pyramid_features,
               create_semantic_head=__create_semantic_head,
               frames_per_batch=1,
               temporal_mode=None,
               num_semantic_heads=1,
               num_semantic_classes=[3],
               required_channels=3,
               norm_method='whole_image',
               pooling=None,
               location=True,
               use_imagenet=True,
               lite=False,
               name='panopticnet',
               **kwargs):
    
    channel_axis = 1 if K.image_data_format() == 'channels_first' else -1
=======

def PanopticNet(backbone,
                input_shape,
                inputs=None,
                backbone_levels=['C3', 'C4', 'C5'],
                pyramid_levels=['P3', 'P4', 'P5', 'P6', 'P7'],
                create_pyramid_features=__create_pyramid_features,
                create_semantic_head=__create_semantic_head,
                frames_per_batch=1,
                temporal_mode=None,
                num_semantic_heads=1,
                num_semantic_classes=[3],
                required_channels=3,
                norm_method='whole_image',
                pooling=None,
                location=True,
                use_imagenet=True,
                lite=False,
                interpolation='bilinear',
                name='panopticnet',
                **kwargs):
    """Constructs a mrcnn model using a backbone from keras-applications.

    Args:
        backbone (str): Name of backbone to use.
        input_shape (tuple): The shape of the input data.
        backbone_levels (list): The backbone levels to be used.
            to create the feature pyramid. Defaults to ['C3', 'C4', 'C5'].
        pyramid_levels (list): Pyramid levels to use. Defaults to
            ['P3','P4','P5','P6','P7']
        create_pyramid_features (function): Function to get the pyramid
            features from the backbone.
        create_semantic_head (function): Function to get to build a
            semantic head submodel.
        frames_per_batch (int): Defaults to 1.
        temporal_mode: Mode of temporal convolution. Choose from
            {'conv','lstm','gru', None}. Defaults to None.
        num_semantic_heads (int): Defaults to 1.
        num_semantic_classes (list): Defaults to [3].
        norm_method (str): ImageNormalization mode to use.
            Defaults to 'whole_image'.
        location (bool): Whether to include location data. Defaults to True
        use_imagenet (bool): Whether to load imagenet-based pretrained weights.
        lite (bool): Whether to use a depthwise conv in the feature pyramid
            rather than regular conv. Defaults to False.
        interpolation (str): Choice of interpolation mode for upsampling
            layers from ['bilinear', 'nearest']. Defaults to bilinear.
        pooling (str): optional pooling mode for feature extraction
            when include_top is False.

            - None means that the output of the model will be
                the 4D tensor output of the
                last convolutional layer.
            - 'avg' means that global average pooling
                will be applied to the output of the
                last convolutional layer, and thus
                the output of the model will be a 2D tensor.
            - 'max' means that global max pooling will
                be applied.

        required_channels (int): The required number of channels of the
            backbone.  3 is the default for all current backbones.
        kwargs (dict): Other standard inputs for retinanet_mask.

    Raises:
        ValueError: temporal_mode not 'conv', 'lstm', 'gru'  or None

    Returns:
        tensorflow.keras.Model: Panoptic model with a backbone.
    """
    channel_axis = 1 if K.image_data_format() == 'channels_first' else -1
    conv = Conv3D if frames_per_batch > 1 else Conv2D
    conv_kernel = (1, 1, 1) if frames_per_batch > 1 else (1, 1)

    # Check input to __merge_temporal_features
    acceptable_modes = {'conv', 'lstm', 'gru', None}
    if temporal_mode is not None:
        temporal_mode = str(temporal_mode).lower()
        if temporal_mode not in acceptable_modes:
            raise ValueError('Mode {} not supported. Please choose '
                             'from {}.'.format(temporal_mode,
                                               str(acceptable_modes)))

    # Check input to interpolation
    acceptable_interpolation = {'bilinear', 'nearest'}
    if interpolation not in acceptable_interpolation:
        raise ValueError('Interpolation mode not supported. Choose from '
                         '["bilinear", "nearest"]')
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e

    if inputs is None:
        if frames_per_batch > 1:
            if channel_axis == 1:
                input_shape_with_time = tuple(
                    [input_shape[0], frames_per_batch] + list(input_shape)[1:])
            else:
                input_shape_with_time = tuple(
                    [frames_per_batch] + list(input_shape))
            inputs = Input(shape=input_shape_with_time, name='input_0')
        else:
            inputs = Input(shape=input_shape, name='input_0')

<<<<<<< HEAD
    # force the channel size for backbone input to be `required_channels`
=======
    # Normalize input images
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    if norm_method is None:
        norm = inputs
    else:
        if frames_per_batch > 1:
<<<<<<< HEAD
            norm = TimeDistributed(ImageNormalization2D(norm_method=norm_method, name='norm'))(inputs)
        else:
            norm = ImageNormalization2D(norm_method=norm_method, name='norm')(inputs)

    if location:
        if frames_per_batch > 1:
            # TODO: TimeDistributed is incompatible with channels_first
            loc = TimeDistributed(Location2D(in_shape=input_shape))(norm)
        else:
            loc = Location2D(in_shape=input_shape, name='location')(norm)
        concat = Concatenate(axis=channel_axis, name='concatenate_location')([norm, loc])
    else:
        concat = norm

    if frames_per_batch > 1:
        fixed_inputs = Conv3D(required_channels, (1,1,1), strides=1, 
                                padding='same', name='tensor_product_channels')(concat)
    else:
        fixed_inputs = Conv2D(required_channels, (1,1), strides=1, 
                                padding='same', name='tensor_product_channels')(concat)
                                
    # if frames_per_batch > 1:
    #     fixed_inputs = TimeDistributed(TensorProduct(required_channels, name='tensor_product_channels'))(concat)
    # else:
    #     fixed_inputs = TensorProduct(required_channels, name='tensor_product_channels')(concat)

    # force the input shape
=======
            norm = TimeDistributed(ImageNormalization2D(
                norm_method=norm_method, name='norm'))(inputs)
        else:
            norm = ImageNormalization2D(norm_method=norm_method,
                                        name='norm')(inputs)

    # Add location layer
    if location:
        if frames_per_batch > 1:
            # TODO: TimeDistributed is incompatible with channels_first
            loc = TimeDistributed(Location2D(in_shape=input_shape,
                                             name='location'))(norm)
        else:
            loc = Location2D(in_shape=input_shape, name='location')(norm)
        concat = Concatenate(axis=channel_axis,
                             name='concatenate_location')([norm, loc])
    else:
        concat = norm

    # Force the channel size for backbone input to be `required_channels`
    fixed_inputs = conv(required_channels, conv_kernel, strides=1,
                        padding='same', name='conv_channels')(concat)

    # Force the input shape
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    axis = 0 if K.image_data_format() == 'channels_first' else -1
    fixed_input_shape = list(input_shape)
    fixed_input_shape[axis] = required_channels
    fixed_input_shape = tuple(fixed_input_shape)

    model_kwargs = {
        'include_top': False,
        'weights': None,
        'input_shape': fixed_input_shape,
        'pooling': pooling
    }

    _, backbone_dict = get_backbone(backbone, fixed_inputs,
                                    use_imagenet=use_imagenet,
                                    frames_per_batch=frames_per_batch,
                                    return_dict=True, **model_kwargs)

    backbone_dict_reduced = {k: backbone_dict[k] for k in backbone_dict
                             if k in backbone_levels}
    ndim = 2 if frames_per_batch == 1 else 3
<<<<<<< HEAD
    pyramid_dict = create_pyramid_features(backbone_dict_reduced, ndim=ndim, lite=True)

    features = [pyramid_dict[key] for key in pyramid_levels]  

    if frames_per_batch > 1:
        if temporal_mode in ['conv', 'lstm', 'gru']:
            temporal_features = [__merge_temporal_features(feature, mode=temporal_mode) for feature in features]
            for f, k in zip(temporal_features, pyramid_dict.keys()):
                pyramid_dict[k] = f
=======
    pyramid_dict = create_pyramid_features(backbone_dict_reduced,
                                           ndim=ndim,
                                           lite=lite,
                                           upsample_type='upsampling2d')

    features = [pyramid_dict[key] for key in pyramid_levels]

    if frames_per_batch > 1:
        temporal_features = [__merge_temporal_features(
            feature, mode=temporal_mode) for feature in features]
        for f, k in zip(temporal_features, pyramid_dict.keys()):
            pyramid_dict[k] = f
>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e

    semantic_levels = [int(re.findall(r'\d+', k)[0]) for k in pyramid_dict]
    target_level = min(semantic_levels)

    semantic_head_list = []
    for i in range(num_semantic_heads):
        semantic_head_list.append(create_semantic_head(
            pyramid_dict, n_classes=num_semantic_classes[i],
            input_target=inputs, target_level=target_level,
<<<<<<< HEAD
            semantic_id=i, ndim=ndim, **kwargs)) 
    
    outputs=semantic_head_list
    
=======
            semantic_id=i, ndim=ndim, **kwargs))

    outputs = semantic_head_list

>>>>>>> 890b7cd85983eb2811c5b0689431267df6e5f66e
    model = Model(inputs=inputs, outputs=outputs, name=name)
    return model
