vllm server /data1/hf-models/Qwen3/Qwen3-0.6B --port 8080 --dtype bfloat16 --tensor-parallel-size 4 --trust-remote-code


# tensor-parallel-size 为并行数，建议和显卡数量相同，如果 attention heads 不能被 tensor-parallel-size 整除，则可以通过增加 --pipeline-parallel-size 2 参数来解决 (8卡时 pipeline-parallel-size 取2，即每个节点4卡，2节点8卡)

# --dtype bfloat16 代表使用 bf16 精度，模型不支持时去掉