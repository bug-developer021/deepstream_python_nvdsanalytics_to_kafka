# pyds-kafka
通过编译deepstream  NvDsEventMsgMeta以及eventmsg_payload来将NvAnalytics数据发送到kafka

## how to run
- clone此项目，并将pyds_kafka_exmaple移动到`/opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps/apps/`路径下

- 运行代码
  ```python
  python3 run.py -i /opt/nvidia/deepstream/deepstream-6.1/samples/streams/sample_720p.h264 -p /opt/nvidia/deepstream/deepstream-6.1/lib/libnvds_kafka_proto.so --conn-str="localhost;9092;ds-kafka" -s 0 --no-display
  ```


- 输出的schema
```json
{
  "messageid" : "b99617a2-226d-49fa-9f38-a23bf5de91cd",
  "@timestamp" : "2022-08-12T06:50:59.006Z",
  "deviceId" : "device_test",
  "analyticsModule" : {
    "stream_source_id" : 0,
    "lc_curr_straight" : 0,
    "lc_curr_left" : 0,
    "lc_curr_right" : 0,
    "lc_cum_straight" : 38,
    "lc_cum_left" : 0,
    "lc_cum_right" : 0
  }
}
```