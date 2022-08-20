# Send analytics data to kafka use deepstream python

# Contents  
- [Description](#description)  
- [How to run](#how-to-run)  
  - [Build and run docker images](#build-and-run-docker-images)
  - [Run deepstream python script](#run-deepstream-python-script)
  - [Consume messages](#consume-messages)
- [Details](#details)
  - [Add analytics msg meta to NvDsEventMsgMeta](#add-analytics-msg-meta-to-nvdseventmsgmeta)
  - [Remake libnvds_msgconv.so](#remake-libnvdsmsgconvso)
  - [Build and install Python bindings](#build-and-install-python-bindings)

# Description
The [deepstream-occupancy-analytics](https://github.com/NVIDIA-AI-IOT/deepstream-occupancy-analytics) repo provides a method to send analytics data to kafka, but it is C version. It's not esay for python programmer who don't have enough time to figure out how to use it. In deepstream forums, the maintainer said deepstream python will support custom message payload feature in the future release.   

By referring to [How do I change JSON payload output?](https://forums.developer.nvidia.com/t/how-do-i-change-json-payload-output/217386/4) and [Problem with reading nvdsanalytics output via Kafka](https://forums.developer.nvidia.com/t/problem-with-reading-nvdsanalytics-output-via-kafka/154071), I make some changes of C source code,  insert custom `lc_curr_straight` and `lc_cum_straight` in NvDsEventMsgMeta and send to kafka. Then build the deepstream python bindings. 

The only thing to send line-crossing data is to assign analytics data to  `msg_meta.lc_curr_straight` and  `msg_meta.lc_cum_straight`, the key of dict is depend on nvdsanalytics config

```python
msg_meta.lc_curr_straight = obj_lc_curr_cnt["straight"]
msg_meta.lc_cum_straight = obj_lc_cum_cnt["straight"] 
```

Actually, There is a simple way to send custom meesages. If you don't need to process scale of video streams, or the latency is not important, you can use [kafka-python library](https://forums.developer.nvidia.com/t/how-to-build-a-custom-object-to-use-on-payloads-for-message-broker-with-python-bindings/171193) to send messages instead of use `nvmsgconv` and `nvmsgbroker`.   

If not , you should go back to modeify the C source code and build it. Since the probe is a blocking operation, it is not suitable for complex processing. 



# How to run
**If you want custom you own messages, you can refer to [Details](#details)**

## Build  and run docker images   
 - clone this repo, in deepstream_python_nvdsanalytics_to_kafka workpace, run `sh docker/build.sh <image_name>` to build a docker image, e.g:
`sh docker/build.sh  deepstream:6.1-triton-jupyter-python-custom`

 - run the docker image and access jupyter  
    ```shell
    docker run --gpus  device=0  -p 8888:8888 -it --rm --shm-size=1g  -w /opt/nvidia/deepstream/deepstream-6.1/sources/mount/   -v ~/deepstream_python_nvdsanalytics_to_kafka/:/opt/nvidia/deepstream/deepstream-6.1/sources/mount  deepstream:6.1-triton-jupyter-python-custom
    ```
    type `http://<host_ip>:8888` on browser to access jupyter  

 - (optional) on kubernetes master node, run `sh /docker/ds-jupyter-statefulset.sh` to launch deepstream instance on kubernetes. The premise is that `nvidia-device-plugin` is installed on your kubernetes


## Run deepstream python script
the deepstream python pipeline of `/pyds_kafka_example/run.py` is base on `deepstream-test4` and `deepstream-nvdsanalytics`

 - before running, set the `partion-key = deviceId` in `pyds_kafka_example/cfg_kafka.txt`, it will set partition-key by the deviceId of payload to be sent

 - cd `pyds_kafka_example` path and run the python script, e.g:
    ```shell
    python3 run.py -i /opt/nvidia/deepstream/deepstream-6.1/samples/streams/sample_720p.h264 -p /opt/nvidia/deepstream/deepstream-6.1/lib/libnvds_kafka_proto.so --conn-str="localhost;9092;ds-kafka" -s 0 --no-display
    ```
    the deepstrem python pipeline architecture is as follows:
    ![](./assets/ds-pipeline.svg)


## Consume messages
  open an new ternimal to consume messages

  ```shell
  bin/kafka-console-consumer.sh --topic ds-kafka --from-beginning --bootstrap-server localhost:9092
  ```

  The output will look like this:


  ```json
  {
    "messageid" : "b99617a2-226d-49fa-9f38-a23bf5de91cd",
    "@timestamp" : "2022-08-12T06:50:59.006Z",
    "deviceId" : "device_test",
    "analyticsModule" : {
      "stream_source_id" : 0,
      "lc_curr_straight" : 0,
      "lc_cum_straight" : 38
    }
  }
  ```



# Details
## Add analytics msg meta to NvDsEventMsgMeta

In L232 of `nvdsmeta_schema.h`, insert custom analytics msg meta of `typedef struct NvDsEventMsgMeta` :

```cpp
  guint lc_curr_straight;
  guint lc_cum_straight;
```

## Remake `libnvds_msgconv.so`  

- deepstream_schema  
  In `/opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv`, add same analytics msg meta  in `nvmsgconv/deestream_schema/deepstream_schema.h` at L93 of `struct NvDsAnalyticsObject`

  ```cpp
    guint lc_curr_straight;
    guint lc_cum_straight;
  ```

- eventmsg_payload  
  The most important step of cutstom your message payload. in  `nvmsgconv/deepstream_schema/eventmsg_payload`, your can insert your analytics msg meta in the `generate_analytics_module_object` function at L186:
  ```cpp
    // custom analytics data
    json_object_set_double_member (analyticsObj, "lc_curr_straight", meta->lc_curr_straight);
    json_object_set_double_member (analyticsObj, "lc_cum_straight", meta->lc_cum_straight);
  ```

  You can also comment some payload that your don't want to send to kafka. In `generate_event_message`  function at L536:

  ```cpp
  // // place object
  // placeObj = generate_place_object (privData, meta);

  // // sensor object
  // sensorObj = generate_sensor_object (privData, meta);

  // analytics object
  analyticsObj = generate_analytics_module_object (privData, meta);

  // // object object
  // objectObj = generate_object_object (privData, meta);

  // // event object
  // eventObj = generate_event_object (privData, meta);

  // root object
  rootObj = json_object_new ();
  json_object_set_string_member (rootObj, "messageid", msgIdStr);
  // json_object_set_string_member (rootObj, "mdsversion", "1.0");
  json_object_set_string_member (rootObj, "@timestamp", meta->ts);

  // use the orginal params sensorStr in NvDsEventMsgMeta to accept deviceId that generated by python script
  json_object_set_string_member (rootObj, "deviceId", meta->sensorStr);
  // json_object_set_object_member (rootObj, "place", placeObj);
  // json_object_set_object_member (rootObj, "sensor", sensorObj);
  json_object_set_object_member (rootObj, "analyticsModule", analyticsObj);

  // not use these metadata
  // json_object_set_object_member (rootObj, "object", objectObj);
  // json_object_set_object_member (rootObj, "event", eventObj);

  // if (meta->videoPath)
  //   json_object_set_string_member (rootObj, "videoPath", meta->videoPath);
  // else
  //   json_object_set_string_member (rootObj, "videoPath", "");
  ```

- rebuild custom payload for sending messages to kafka
  ```shell
  cd /opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv \
  && make \
  && cp libnvds_msgconv.so /opt/nvidia/deepstream/deepstream/lib/libnvds_msgconv.so
  ```


## Build and install Python bindings  
  
In L426 of `bindschema.cpp` , insert the following code before build deepstream python bindings  
```cpp
  .def_readwrite("lc_curr_straight", &NvDsEventMsgMeta::lc_curr_straight)
  .def_readwrite("lc_cum_straight", &NvDsEventMsgMeta::lc_cum_straight);
```
then build deepstream python bindings and pip install it, more install detail please refer to `/docker/Dockerfile`