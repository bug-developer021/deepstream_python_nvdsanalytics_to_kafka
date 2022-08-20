#!/usr/bin/env python3

################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2019-2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import sys
import gi
import configparser
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst
import sys
from optparse import OptionParser
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call
from common.utils import long_to_uint64
import pyds

MAX_DISPLAY_LEN = 64
MAX_TIME_STAMP_LEN = 32
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH = 1920
MUXER_OUTPUT_HEIGHT = 1080
MUXER_BATCH_TIMEOUT_USEC = 4000000
input_file = None
schema_type = 0
proto_lib = None
conn_str = "localhost;2181;testTopic"
cfg_file = None
topic = None
no_display = False

PGIE_CONFIG_FILE = "dstest4_pgie_config.txt"
MSCONV_CONFIG_FILE = "dstest4_msgconv_config.txt"

TRACKER_CONFIG_FILE = "dsnvanalytics_tracker_config.txt"
pgie_classes_str = ["Vehicle", "TwoWheeler", "Person", "Roadsign"]


# Callback function for deep-copying an NvDsEventMsgMeta struct
def meta_copy_func(data, user_data):
    # Cast data to pyds.NvDsUserMeta
    user_meta = pyds.NvDsUserMeta.cast(data)
    src_meta_data = user_meta.user_meta_data
    # Cast src_meta_data to pyds.NvDsEventMsgMeta
    srcmeta = pyds.NvDsEventMsgMeta.cast(src_meta_data)
    # Duplicate the memory contents of srcmeta to dstmeta
    # First use pyds.get_ptr() to get the C address of srcmeta, then
    # use pyds.memdup() to allocate dstmeta and copy srcmeta into it.
    # pyds.memdup returns C address of the allocated duplicate.
    dstmeta_ptr = pyds.memdup(pyds.get_ptr(srcmeta),
                              sys.getsizeof(pyds.NvDsEventMsgMeta))
    # Cast the duplicated memory to pyds.NvDsEventMsgMeta
    dstmeta = pyds.NvDsEventMsgMeta.cast(dstmeta_ptr)

    # Duplicate contents of ts field. Note that reading srcmeat.ts
    # returns its C address. This allows to memory operations to be
    # performed on it.
    dstmeta.ts = pyds.memdup(srcmeta.ts, MAX_TIME_STAMP_LEN + 1)

    if srcmeta.objSignature.size > 0:
        dstmeta.objSignature.signature = pyds.memdup(
            srcmeta.objSignature.signature, srcmeta.objSignature.size)
        dstmeta.objSignature.size = srcmeta.objSignature.size

    return dstmeta


# Callback function for freeing an NvDsEventMsgMeta instance
def meta_free_func(data, user_data):
    user_meta = pyds.NvDsUserMeta.cast(data)
    srcmeta = pyds.NvDsEventMsgMeta.cast(user_meta.user_meta_data)

    # pyds.free_buffer takes C address of a buffer and frees the memory
    # It"s a NOP if the address is NULL
    pyds.free_buffer(srcmeta.ts)

    if srcmeta.objSignature.size > 0:
        pyds.free_buffer(srcmeta.objSignature.signature)
        srcmeta.objSignature.size = 0




def generate_event_msg_meta(data):
    meta = pyds.NvDsEventMsgMeta.cast(data)
    meta.ts = pyds.alloc_buffer(MAX_TIME_STAMP_LEN + 1)
    pyds.generate_ts_rfc3339(meta.ts, MAX_TIME_STAMP_LEN)


    return meta


# osd_sink_pad_buffer_probe  will extract metadata received on OSD sink pad
# and update params for drawing rectangle, object information etc.
# IMPORTANT NOTE:
# a) probe() callbacks are synchronous and thus holds the buffer
#    (info.get_buffer()) from traversing the pipeline until user return.
# b) loops inside probe() callback could be costly in python.
#    So users shall optimize according to their use-case.
def osd_sink_pad_buffer_probe(pad, info, u_data):
    frame_number = 0
    # Intiallizing object counter with 0.
    obj_counter = {
        PGIE_CLASS_ID_VEHICLE: 0,
        PGIE_CLASS_ID_PERSON: 0,
        PGIE_CLASS_ID_BICYCLE: 0,
        PGIE_CLASS_ID_ROADSIGN: 0
    }
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.NvDsFrameMeta.cast()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            continue

        l_user = frame_meta.frame_user_meta_list
        source_id = frame_meta.pad_index
        frame_number = frame_meta.frame_num

        # Short example of attribute access for frame_meta:
        # print("Frame Number is ", frame_meta.frame_num)
        # print("Source id is ", frame_meta.source_id)
        # print("Batch id is ", frame_meta.batch_id)
        # print("Source Frame Width ", frame_meta.source_frame_width)
        # print("Source Frame Height ", frame_meta.source_frame_height)
        # print("Num object meta ", frame_meta.num_obj_meta)

        while l_user:
            try:
                user_meta = pyds.NvDsUserMeta.cast(l_user.data)
                if user_meta.base_meta.meta_type == pyds.nvds_get_user_meta_type("NVIDIA.DSANALYTICSFRAME.USER_META"):
                    user_meta_data = pyds.NvDsAnalyticsFrameMeta.cast(
                        user_meta.user_meta_data)

                    if user_meta_data.objLCCumCnt: print("Linecrossing Cumulative: {0}".format(user_meta_data.objLCCumCnt))
                    if user_meta_data.objLCCurrCnt: print("Linecrossing Current Frame: {0}".format(user_meta_data.objLCCurrCnt))


                    # linecrossing cumulative
                    obj_lc_cum_cnt = user_meta_data.objLCCumCnt
                    # linecrossing current frame
                    obj_lc_curr_cnt = user_meta_data.objLCCurrCnt

            
                    # Ideally NVDS_EVENT_MSG_META should be attached to buffer by the
                    # component implementing detection / recognition logic.
                    # Here it demonstrates how to use / attach that meta data.
                    # Frequency of messages to be send will be based on use case.
                    # Here message is being sent for first object every 30 frames.

                    # Allocating an NvDsEventMsgMeta instance and getting
                    # reference to it. The underlying memory is not manged by
                    # Python so that downstream plugins can access it. Otherwise
                    # the garbage collector will free it when this probe exits.
                    curr_cnt_sum = sum([ obj_lc_curr_cnt[i] for i in obj_lc_curr_cnt])
                    # if frame_number % 30 == 0:
                    if curr_cnt_sum > 0:
                        msg_meta = pyds.alloc_nvds_event_msg_meta()
                        # you can assign your own device ID here
                        msg_meta.sensorStr = "device_test"

                        if obj_lc_curr_cnt.get("straight"):  msg_meta.lc_curr_straight = obj_lc_curr_cnt["straight"]
                        if obj_lc_cum_cnt.get("straight") :  msg_meta.lc_cum_straight = obj_lc_cum_cnt["straight"] 

                        msg_meta = generate_event_msg_meta(msg_meta)
                        user_event_meta = pyds.nvds_acquire_user_meta_from_pool(
                            batch_meta)
                        if user_event_meta:
                            user_event_meta.user_meta_data = msg_meta
                            user_event_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_EVENT_MSG_META
                            # Setting callbacks in the event msg meta. The bindings
                            # layer will wrap these callables in C functions.
                            # Currently only one set of callbacks is supported.
                            pyds.user_copyfunc(user_event_meta, meta_copy_func)
                            pyds.user_releasefunc(user_event_meta, meta_free_func)
                            pyds.nvds_add_user_meta_to_frame(frame_meta,
                                                                user_event_meta)
                        else:
                            print("Error in attaching event meta to buffer\n")

            except StopIteration:
                continue
            try:
                l_user = l_user.next
            except StopIteration:
                break

        # Update frame rate through this probe
        # stream_index = "stream{0}".format(frame_meta.pad_index)
        # global perf_data
        # perf_data.update_fps(stream_index)
        try:
            l_frame = l_frame.next
        except StopIteration:
            break


    return Gst.PadProbeReturn.OK


def main(args):
    Gst.init(None)

    # registering callbacks
    pyds.register_user_copyfunc(meta_copy_func)
    pyds.register_user_releasefunc(meta_free_func)

    print("Creating Pipeline \n ")

    pipeline = Gst.Pipeline()

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")

    print("Creating Source \n ")
    source = Gst.ElementFactory.make("filesrc", "file-source")
    if not source:
        sys.stderr.write(" Unable to create Source \n")

    print("Creating H264Parser \n")
    h264parser = Gst.ElementFactory.make("h264parse", "h264-parser")
    if not h264parser:
        sys.stderr.write(" Unable to create h264 parser \n")

    print("Creating Decoder \n")
    decoder = Gst.ElementFactory.make("nvv4l2decoder", "nvv4l2-decoder")
    if not decoder:
        sys.stderr.write(" Unable to create Nvv4l2 Decoder \n")

    print("Creating Streammux \n")
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    print("Creating Pgie \n")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")

    ## add tracker and nvdsanalytics
    print("Creating nvtracker \n ")
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    if not tracker:
        sys.stderr.write(" Unable to create tracker \n")

    print("Creating nvdsanalytics \n ")
    nvanalytics = Gst.ElementFactory.make("nvdsanalytics", "analytics")
    if not nvanalytics:
        sys.stderr.write(" Unable to create nvanalytics \n")
    nvanalytics.set_property("config-file", "config_nvdsanalytics.txt")

    print("Creating nvvidconv \n ")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write(" Unable to create nvvidconv \n")

    print("Creating nvdsosd \n ")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write(" Unable to create nvosd \n")

    print("Creating nvmsgconv \n ")
    msgconv = Gst.ElementFactory.make("nvmsgconv", "nvmsg-converter")
    if not msgconv:
        sys.stderr.write(" Unable to create msgconv \n")
    
    print("Creating nvmsgbroker \n ")
    msgbroker = Gst.ElementFactory.make("nvmsgbroker", "nvmsg-broker")
    if not msgbroker:
        sys.stderr.write(" Unable to create msgbroker \n")

    print("Creating tee\n ")
    tee = Gst.ElementFactory.make("tee", "nvsink-tee")
    if not tee:
        sys.stderr.write(" Unable to create tee \n")

    print("Creating queue1\n ")
    queue1 = Gst.ElementFactory.make("queue", "nvtee-que1")
    if not queue1:
        sys.stderr.write(" Unable to create queue1 \n")

    print("Creating queue2\n ")
    queue2 = Gst.ElementFactory.make("queue", "nvtee-que2")
    if not queue2:
        sys.stderr.write(" Unable to create queue2 \n")

    if no_display:
        print("Creating FakeSink \n")
        sink = Gst.ElementFactory.make("fakesink", "fakesink")
        if not sink:
            sys.stderr.write(" Unable to create fakesink \n")
    else:
        if is_aarch64():
            transform = Gst.ElementFactory.make("nvegltransform",
                                                "nvegl-transform")

        print("Creating EGLSink \n")
        sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
        if not sink:
            sys.stderr.write(" Unable to create egl sink \n")

    print("Playing file %s " % input_file)
    source.set_property("location", input_file)
    streammux.set_property("width", MUXER_OUTPUT_WIDTH)
    streammux.set_property("height", MUXER_OUTPUT_HEIGHT)
    streammux.set_property("batch-size", 1)
    streammux.set_property("batched-push-timeout", 40000)
    pgie.set_property("config-file-path", PGIE_CONFIG_FILE)


    #Set properties of tracker
    config = configparser.ConfigParser()
    config.read(TRACKER_CONFIG_FILE)
    config.sections()

    for key in config["tracker"]:
        if key == "tracker-width" :
            tracker_width = config.getint("tracker", key)
            tracker.set_property("tracker-width", tracker_width)
        if key == "tracker-height" :
            tracker_height = config.getint("tracker", key)
            tracker.set_property("tracker-height", tracker_height)
        if key == "gpu-id" :
            tracker_gpu_id = config.getint("tracker", key)
            tracker.set_property("gpu_id", tracker_gpu_id)
        if key == "ll-lib-file" :
            tracker_ll_lib_file = config.get("tracker", key)
            tracker.set_property("ll-lib-file", tracker_ll_lib_file)
        if key == "ll-config-file" :
            tracker_ll_config_file = config.get("tracker", key)
            tracker.set_property("ll-config-file", tracker_ll_config_file)
        if key == "enable-batch-process" :
            tracker_enable_batch_process = config.getint("tracker", key)
            tracker.set_property("enable_batch_process", tracker_enable_batch_process)
        if key == "enable-past-frame" :
            tracker_enable_past_frame = config.getint("tracker", key)
            tracker.set_property("enable_past_frame", tracker_enable_past_frame)

    msgconv.set_property("config", MSCONV_CONFIG_FILE)
    msgconv.set_property("payload-type", schema_type)
    msgbroker.set_property("proto-lib", proto_lib)
    msgbroker.set_property("conn-str", conn_str)
    if cfg_file is not None:
        msgbroker.set_property("config", cfg_file)
    if topic is not None:
        msgbroker.set_property("topic", topic)
    msgbroker.set_property("sync", False)

    print("Adding elements to Pipeline \n")
    pipeline.add(source)
    pipeline.add(h264parser)
    pipeline.add(decoder)
    pipeline.add(streammux)
    pipeline.add(pgie)
    
    pipeline.add(tracker)
    pipeline.add(nvanalytics)
    
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(tee)
    pipeline.add(queue1)
    pipeline.add(queue2)
    pipeline.add(msgconv)
    pipeline.add(msgbroker)
    pipeline.add(sink)
    if is_aarch64() and not no_display:
        pipeline.add(transform)

    print("Linking elements in the Pipeline \n")
    source.link(h264parser)
    h264parser.link(decoder)

    sinkpad = streammux.get_request_pad("sink_0")
    if not sinkpad:
        sys.stderr.write(" Unable to get the sink pad of streammux \n")
    srcpad = decoder.get_static_pad("src")
    if not srcpad:
        sys.stderr.write(" Unable to get source pad of decoder \n")
    srcpad.link(sinkpad)

    streammux.link(pgie)
    # pgie.link(nvvidconv)
    pgie.link(tracker)
    tracker.link(nvanalytics)
    nvanalytics.link(nvvidconv)
    
    nvvidconv.link(nvosd)
    nvosd.link(tee)
    queue1.link(msgconv)
    msgconv.link(msgbroker)
    if is_aarch64() and not no_display:
        queue2.link(transform)
        transform.link(sink)
    else:
        queue2.link(sink)
    sink_pad = queue1.get_static_pad("sink")
    tee_msg_pad = tee.get_request_pad("src_%u")
    tee_render_pad = tee.get_request_pad("src_%u")
    if not tee_msg_pad or not tee_render_pad:
        sys.stderr.write("Unable to get request pads\n")
    tee_msg_pad.link(sink_pad)
    sink_pad = queue2.get_static_pad("sink")
    tee_render_pad.link(sink_pad)

    # create an event loop and feed gstreamer bus messages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # osdsinkpad = nvosd.get_static_pad("sink")
    # if not osdsinkpad:
    #     sys.stderr.write(" Unable to get sink pad of nvosd \n")



    # custom insert  
    nvanalytics_src_pad=nvanalytics.get_static_pad("src")
    nvanalytics_src_pad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)




    print("Starting pipeline \n")

    # start play back and listed to events
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    pyds.unset_callback_funcs()
    pipeline.set_state(Gst.State.NULL)


# Parse and validate input arguments
def parse_args():
    parser = OptionParser()
    parser.add_option("-c", "--cfg-file", dest="cfg_file",
                      help="Set the adaptor config file. Optional if "
                           "connection string has relevant  details.",
                      metavar="FILE")
    parser.add_option("-i", "--input-file", dest="input_file",
                      help="Set the input H264 file", metavar="FILE")
    parser.add_option("-p", "--proto-lib", dest="proto_lib",
                      help="Absolute path of adaptor library", metavar="PATH")
    parser.add_option("", "--conn-str", dest="conn_str",
                      help="Connection string of backend server. Optional if "
                           "it is part of config file.", metavar="STR")
    parser.add_option("-s", "--schema-type", dest="schema_type", default="0",
                      help="Type of message schema (0=Full, 1=minimal), "
                           "default=0", metavar="<0|1>")
    parser.add_option("-t", "--topic", dest="topic",
                      help="Name of message topic. Optional if it is part of "
                           "connection string or config file.", metavar="TOPIC")
    parser.add_option("", "--no-display", action="store_true",
                      dest="no_display", default=False,
                      help="Disable display")

    (options, args) = parser.parse_args()

    global cfg_file
    global input_file
    global proto_lib
    global conn_str
    global topic
    global schema_type
    global no_display
    cfg_file = options.cfg_file
    input_file = options.input_file
    proto_lib = options.proto_lib
    conn_str = options.conn_str
    topic = options.topic
    no_display = options.no_display

    if not (proto_lib and input_file):
        print("Usage: python3 deepstream_test_4.py -i <H264 filename> -p "
              "<Proto adaptor library> --conn-str=<Connection string>")
        return 1

    schema_type = 0 if options.schema_type == "0" else 1


if __name__ == "__main__":
    ret = parse_args()
    # If argument parsing fails, returns failure (non-zero)
    if ret == 1:
        sys.exit(1)
    sys.exit(main(sys.argv))