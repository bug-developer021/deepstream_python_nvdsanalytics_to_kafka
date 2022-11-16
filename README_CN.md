# 利用deepstream python将analytics产生的统计数据发送到kafka
Zh-CN | [English](README.md) 

# 目录  
- [概述](#概述)  
- [运行环境](#运行环境)
- [如何运行](#如何运行)  
  - [构建docker镜像并运行](#构建docker镜像并运行)
  - [运行deepstream python推送消息](#运行deepstream-python推送消息)
  - [消费kafka数据](#消费kafka数据)
- [主要改动](#主要改动)
  - [在NvDsEventMsgMeta结构里添加analytics msg meta](#在nvdseventmsgmeta结构里添加analytics-msg-meta)
  - [编译libnvds_msgconv.so](#编译libnvds_msgconvso)
  - [编译Python bindings](#编译python-bindings)
- [参考文档](#参考文档)


# 概述
[deepstream-occupancy-analytics](https://github.com/NVIDIA-AI-IOT/deepstream-occupancy-analytics)项目提供了一种往kafka发送analytics统计数据的方法。但是所有的改动，特别是主程序是用C语言开发的。但写这篇文章的时候，在网上还没发现官方系统性的说明和解释，都是一些零碎的问答。

因此综合[参考文档](#参考文档)，以跨线统计为例，本项目提供了一种python版本发送统计数据的方法，同时详细说明了需要改动和编译哪些C程序以及deepstream python bindings。可以参考[主要改动](#主要改动)定制化自己想要收集并发送的数据内容和格式。

改动的地方不多，但对于没接触过C语言的人来说，需要花费一些时间，因此下面记录了探索的过程。

> 论坛上有人回复说，在以后的release中，将会提供基于deepstream python发送自定义数据的功能

主要改动分为三点：

 1. [将自定义的数据结构追加到NvDsEventMsgMeta](#在nvdseventmsgmeta结构里添加analytics-msg-meta)，例如将`lc_curr_straight`和`lc_cum_straight`加入
 2. [修改eventmsg_payload程序](#编译libnvds_msgconvso)，编译产生`libnvds_msgconv.so`
 3. [同步更改bindschema.cpp](#编译python-bindings), 编译deepstream python bindings

最后只需要在python程序中加入如下代码即可发送自定义的统计数据：

```python
# line crossing current count of frame
obj_lc_curr_cnt = user_meta_data.objLCCurrCnt
# line crossing cumulative count
obj_lc_cum_cnt = user_meta_data.objLCCumCnt
msg_meta.lc_curr_straight = obj_lc_curr_cnt["straight"]
msg_meta.lc_cum_straight = obj_lc_cum_cnt["straight"] 
```
> obj_lc_curr_cnt和obj_lc_cum_cnt的key在config_nvdsananlytics.txt中定义

还有一种更简单的方案。如果场景需求中，时延并不重要，也不需要同时处理大规模视频流的话，可以考虑使用[`kafka-python`](https://forums.developer.nvidia.com/t/how-to-build-a-custom-object-to-use-on-payloads-for-message-broker-with-python-bindings/171193) 等python库，直接将获取到的analytics发送出去，不经过`nvmsgconv`和`nvmsgbroker`这两个插件。
如果时延重要，或者要处理大规模视频流，则需要参考下文微调一下C的源代码，重新编译，因为探针函数是阻塞的，并不适合在里面加入复杂的处理逻辑。


# 运行环境
- nvidia-docker2 
- deepstream-6.1



# 如何运行

**如果想插入自定义的消息，请直接参考[主要改动](#主要改动)**


## 构建docker镜像并运行  

 - clone 该代码仓库, 在`deepstream_python_nvdsanalytics_to_kafka`目录, 运行 `sh docker/build.sh <image_name>` 构建镜像, e.g:
`sh docker/build.sh  deepstream:6.1-triton-jupyter-python-custom`

 - 运行docker镜像并进入jupyter环境  
    ```shell
    docker run --gpus  device=0  -p 8888:8888 -d --shm-size=1g  -w /opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps/mount/   -v ~/deepstream_python_nvdsanalytics_to_kafka/:/opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps/mount  deepstream:6.1-triton-jupyter-python-custom
    ```
    浏览器输入`http://<host_ip>:8888`进入jupyter开发环境  

 - (可选) 在kubernetes的master节点, 运行 `sh /docker/ds-jupyter-statefulset.sh` 启动一个deepstream实例. 前提是集群已部署 `nvidia-device-plugin`


## 运行deepstream python推送消息
deepstream python pipeline位于`/pyds_kafka_example/run.py` ，主要参考 `deepstream-test4` 和 `deepstream-nvdsanalytics`

pipeline主要结构如下:
![](./assets/ds-pipeline.svg)

 - 运行前，需要在`pyds_kafka_example/cfg_kafka.txt`里修改partition-key的值，设置为deviceId，这样nvmsgbroker插件会将消息体中deviceId对应的值设置为partition-key

 - 安装java  
   `apt update && apt install -y openjdk-11-jdk`

 - 如果没有单独的kafka集群，请参考[https://kafka.apache.org/quickstart]在deepstream实例中部署kafka并创建topic
    ```shell
    tar -xzf kafka_2.13-3.2.1.tgz
    cd kafka_2.13-3.2.1
    bin/zookeeper-server-start.sh config/zookeeper.properties
    bin/kafka-server-start.sh config/server.properties
    bin/kafka-topics.sh --create --topic ds-kafka --bootstrap-server localhost:9092
    ```

 - 进入 `pyds_kafka_example` 目录运行deepstream python pipeline, e.g:
    ```shell
    python3 run.py -i /opt/nvidia/deepstream/deepstream-6.1/samples/streams/sample_720p.h264 -p /opt/nvidia/deepstream/deepstream-6.1/lib/libnvds_kafka_proto.so --conn-str="localhost;9092;ds-kafka" -s 0 --no-display
    ```



## 消费kafka数据

  ```shell
  # go to kafka_2.13-3.2.1 directory and run
  bin/kafka-console-consumer.sh --topic ds-kafka --from-beginning --bootstrap-server localhost:9092
  ```

  输入如下:

  ```json
  {
    "messageid" : "34359fe1-fa36-4268-b6fc-a302dbab8be9",
    "@timestamp" : "2022-08-20T09:05:01.695Z",
    "deviceId" : "device_test",
    "analyticsModule" : {
      "id" : "XYZ",
      "description" : "\"Vehicle Detection and License Plate Recognition\"",
      "source" : "OpenALR",
      "version" : "1.0",
      "lc_curr_straight" : 1,
      "lc_cum_straight" : 39
    }
  }
  ```



# 主要改动
## 在NvDsEventMsgMeta结构里添加analytics msg meta

在 `nvdsmeta_schema.h`的232行，插入自定义的analytics msg meta到`NvDsEventMsgMeta`结构中

```cpp
  guint lc_curr_straight;
  guint lc_cum_straight;
```

## 编译libnvds_msgconv.so  

- deepstream_schema  

  在`/opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv`目录中，`nvmsgconv/deestream_schema/deepstream_schema.h`文件的93行，加入同样的analytics msg meta定义到`NvDsAnalyticsObject`结构

  ```cpp
    guint lc_curr_straight;
    guint lc_cum_straight;
  ```

- eventmsg_payload


  自定义消息体最重要的一步，在 `nvmsgconv/deepstream_schema/eventmsg_payload.cpp`文件的186行，给`generate_analytics_module_object`函数加入自定义的analytics msg meta

  ```cpp
    // custom analytics data
    // json_object_set_int_member (analyticsObj, 消息体中的key, 消息体中的value);
    json_object_set_int_member (analyticsObj, "lc_curr_straight", meta->lc_curr_straight);
    json_object_set_int_member (analyticsObj, "lc_curr_straight", meta->lc_curr_straight);
    json_object_set_int_member (analyticsObj, "lc_cum_straight", meta->lc_cum_straight);
  ```


  在536行`generate_event_message`函数中，可以注释无效的消息，减小发送消息的大小

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

- 重新编译自定义的libnvds_msgconv.so
  ```shell
  cd /opt/nvidia/deepstream/deepstream/sources/libs/nvmsgconv \
  && make \
  && cp libnvds_msgconv.so /opt/nvidia/deepstream/deepstream/lib/libnvds_msgconv.so
  ```


## 编译Python bindings
  
编译deepstream python binding前，在 `<your own path>/deepstream_python_apps/bindings/src/bindschema.cpp`中，加入对应的msg定义

```cpp
  .def_readwrite("lc_curr_straight", &NvDsEventMsgMeta::lc_curr_straight)
  .def_readwrite("lc_cum_straight", &NvDsEventMsgMeta::lc_cum_straight);
```
接着编译deepstream python binding，并且通过pip安装，更多的操作请参考 `/docker/Dockerfile`

# 参考文档
- [NVIDIA-AI-IOT/deepstream-occupancy-analytics](https://github.com/NVIDIA-AI-IOT/deepstream-occupancy-analytics)
- [deepstream-test4](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/tree/master/apps/deepstream-test4)
- [deepstream-nvdsanalytics](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/tree/master/apps/deepstream-nvdsanalytics)
- [How do I change JSON payload output?](https://forums.developer.nvidia.com/t/how-do-i-change-json-payload-output/217386/4) 
- [Problem with reading nvdsanalytics output via Kafka](https://forums.developer.nvidia.com/t/problem-with-reading-nvdsanalytics-output-via-kafka/154071)