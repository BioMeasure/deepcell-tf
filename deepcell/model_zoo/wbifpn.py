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
"""Weighted bidirectional feature pyramid network utility functions"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

import re

from tensorflow.python.keras.layers import Conv2D, DepthwiseConv2D
from tensorflow.python.keras.layers import Add
from tensorflow.python.keras.layers import Activation
from tensorflow.python.keras.layers import MaxPooling2D
from tensorflow.python.keras.layers import UpSampling2D
from tensorflow.python.keras.layers import BatchNormalization

from deepcell.utils.misc_utils import get_sorted_keys


def ConvBlock(feature, feature_size=64, kernel_size=1, strides=1, name='conv_block'):
    x = Conv2D(feature_size, kernel_size=kernel_size,
               strides=strides,
               padding='same',
               use_bias=False,
               name='{}_conv'.format(name))(feature)
    x = BatchNormalization(axis=-1, name='{}_bn'.format(name))(x)
    x = Activation('relu', name='{}_relu'.format(name))(x)
    return x


def DepthwiseConvBlock(feature, kernel_size=3, strides=1, name='depthwise_conv_block'):
    x = DepthwiseConv2D(kernel_size=kernel_size, strides=strides,
                        padding='same',
                        use_bias=False,
                        name='{}_dconv'.format(name))(feature)
    x = BatchNormalization(axis=-1, name='{}_bn'.format(name))(x)
    x = Activation('relu', name='{}_relu'.format(name))(x)
    return x


def __build_inputs(feature_dict, feature_size=64, include_final_layers=False, index=0):
    input_dict = {}

    feature_names = get_sorted_keys(feature_dict)
    feature_names.reverse()
    features = [feature_dict[name] for name in feature_names]

    # Apply conv
    for i,_ in range(len(feature_names)):
        if i == 0 and include_final_layers:
            N = feature_names[0]
            level = int(re.findall(r'\d+', N)[0])
            feature = features[i]
            feature_plus_one = ConvBlock(feature,
                                         kernel_size=3,
                                         strides=(2, 2),
                                         name='BiFPN_{}_P{}'.format(index, level+1))
            feature_plus_two = ConvBlock(feature_plus_one,
                                         kernel_size=3,
                                         strides=(2, 2),
                                         name='BiFPN_{}_P{}'.format(index, level+2))

            input_dict['P{}_in'.format(level+2)] = feature_plus_two
            input_dict['P{}_in'.format(level+1)] = feature_plus_one

        N = feature_names[i]
        level = int(re.findall(r'\d+', N)[0])
        p_name = 'P{}_in'.format(level)
        feature = features[i]

        feature_input = ConvBlock(feature,
                                  feature_size=feature_size,
                                  name='BiFPN_{}_P{}'.format(index, level))

        input_dict[p_name] = feature_input

    return input_dict


def __build_upsample(input_dict, index=0):
    upsample_dict = {}
    td_dict = {}

    input_names = get_sorted_keys(input_dict)
    input_names.reverse()
    inputs = [input_dict[name] for name in input_names]

    for i in range(1, len(input_names)):
        N = input_names[i]
        level = int(re.findall(r'\d+', N)[0])
        p_in = inputs[i]

        if i == 1:
            upsample_dict['P{}_U'.format(level+1)] = UpSampling2D()(inputs[i-1])
        else:
            upsample_dict['P{}_U'.format(
                level+1)] = UpSampling2D()(td_dict['P{}_td'.format(level+1)])

        td = Add()([upsample_dict['P{}_U'.format(level+1)], p_in])
        td = DepthwiseConvBlock(td, kernel_size=3,
                                strides=1,
                                name='BiFPN_{}_U_P{}'.format(index, level))
        td_dict['P{}_td'.format(level)] = td

    return td_dict


def __build_downsample(input_dict, td_dict, index=0):
    downsample_dict = {}
    output_dict = {}

    td_names = get_sorted_keys(td_dict)
    tds = [td_dict[name] for name in td_names]

    for i in range(len(td_names)+1):

        if i < len(td_names):
            N = td_names[i]
            level = int(re.findall(r'\d+', N)[0])

        if i == 0:
            output_dict['P{}'.format(level)] = tds[i]
            downsample_dict['P{}_D'.format(level)] = MaxPooling2D(strides=(2, 2))(tds[i])
        elif i < len(td_names):
            out = Add()([downsample_dict['P{}_D'.format(level-1)],
                         td_dict['P{}_td'.format(level)], input_dict['P{}_in'.format(level)]])
            out = DepthwiseConvBlock(out, kernel_size=3,
                                     strides=1,
                                     name='BiFPN_{}_D_P{}'.format(index, level))
            output_dict['P{}'.format(level)] = out
            downsample_dict['P{}_D'.format(level)] = MaxPooling2D(strides=(2, 2))(out)
        elif i == len(td_names):
            N = td_names[-1]
            level = int(re.findall(r'\d+', N)[0]) + 1
            out = Add()([downsample_dict['P{}_D'.format(level-1)],
                         input_dict['P{}_in'.format(level)]])
            out = DepthwiseConvBlock(out, kernel_size=3,
                                     strides=1,
                                     name='BiFPN_{}_D_P{}'.format(index, level))
            output_dict['P{}'.format(level)] = out

    return output_dict


def __create_bifpn_features(feature_dict,
                            phi=1,
                            feature_size=32,
                            include_final_layers=False,
                            ndim=2):
    acceptable_ndims = {2}
    if ndim not in acceptable_ndims:
        raise ValueError('Only 2 dimensional networks are supported')

    for index in range(phi):
        input_dict = __build_inputs(feature_dict,
            feature_size=feature_size,
            include_final_layers=include_final_layers if index == 0 else False,
            index=index)

        td_dict = __build_upsample(input_dict, index=index)

        feature_dict = __build_downsample(input_dict, td_dict, index=index)

    pyramid_dict = feature_dict

    return pyramid_dict
