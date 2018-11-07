#!/bin/bash
cd /root/zsky
ps -ef|grep simdht_worker.py|grep -v grep|awk '{print $2}'|xargs kill -9
nohup python simdht_worker.py>/root/zsky/spider.log 2>&1&
