#! /bin/bash

export USER_NAME=jovyan
export JUPYTER_NAME=${USER_NAME}-ds-jupyter
export WORK_IMAGE=deepstream:6.1-triton-jupyter-python-custom
export GPU_REQUEST=1
export DEV_PVC_NAME=${USER_NAME}-ds-dev
export SHM_SIZE=1Gi
export NAMESPACE=jupyter
export NFS_SERVER=
# export JUPYTERCMD=jupyter-lab --notebook-dir=/home/ubuntu --ip=0.0.0.0 --no-browser --allow-root --port=8888 --LabApp.token='' --LabApp.password='' --LabApp.allow_origin='*'  --LabApp.base_url='/'

cat > ./${USER_NAME}-jupyter-ds.yaml << EOF
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ${JUPYTER_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: ${JUPYTER_NAME}
spec:
  replicas: 1
  serviceName: ""
  selector:
    matchLabels:
      app: ${JUPYTER_NAME}
  template:
    metadata:
      labels:
        app: ${JUPYTER_NAME}
    spec:
      containers:
      - name: minimal-notebook
        image: ${WORK_IMAGE}
        imagePullPolicy: IfNotPresent
        env:
        - name: JUPYTERCMD
          value: "jupyter-notebook  --notebook-dir=/opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps --ip=0.0.0.0 --no-browser --allow-root --port=8888 --NotebookApp.token='' "
        command: ["/bin/bash"]
        args: ["-c","\$(JUPYTERCMD)"]
        workingDir: /opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps
        ports:
        - containerPort: 8888
          name: notebook-port
          protocol: TCP
        - containerPort: 8554
          name: rtsp-port
          protocol: TCP
        resources:
          limits:
            nvidia.com/gpu: "${GPU_REQUEST}"
        volumeMounts:
          - mountPath: /opt/nvidia/deepstream/deepstream-6.1/sources/deepstream_python_apps/mount
            name: ${DEV_PVC_NAME}-pv
          - mountPath: /dev/shm
            name: cache-volume
      volumes:
        - name: ${DEV_PVC_NAME}-pv
          nfs:
            server: ${NFS_SERVER}
            path: /nfsdata/static/deepstream/${USER_NAME}
        - name: cache-volume
          emptyDir:
            medium: Memory
            sizeLimit: ${SHM_SIZE}
      restartPolicy: Always
---
kind: Service
apiVersion: v1
metadata:
  name: ${JUPYTER_NAME}
  namespace: ${NAMESPACE}
spec:
  type: NodePort
  ports:
    - name: notebook-port
      protocol: TCP
      port: 80
      targetPort: 8888
    - name: rtsp-port
      protocol: TCP
      port: 8554
      targetPort: 8554
  selector:
    app: ${JUPYTER_NAME}
EOF

kubectl apply -f ./${USER_NAME}-jupyter-ds.yaml