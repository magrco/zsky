#!/bin/bash
#By 我本戏子 2017.8


if [ $(id -u) != "0" ]; then
    echo "当前非root用户登录系统， 请使用root用户运行此脚本!"
    exit 1
fi

yum -y install git
git clone https://github.com/wenguonideshou/zsky
cd /root/zsky

if [ $(grep SwapTotal /proc/meminfo|grep -v grep|awk '{print $2}') -eq 0 ];then
        echo "主机没有swap, 将自动创建大小为1G的swap"
        dd if=/dev/zero of=/swapfile count=1024 bs=1MiB&&
        chmod 600 /swapfile&&mkswap /swapfile&&swapon /swapfile&&
        echo '/swapfile   swap    swap    sw  0   0' >> /etc/fstab&&
        echo "swap创建成功!"
else 
    echo  "存在swap"
fi

read -p "请输入单个域名,不能有空格:" domain
if  [ -z "$domain" ] ;then
    echo "输入域名错误"
    read -p "请输入单个域名,不能有空格:" domain
else
    echo "域名: $domain"
fi

read -p "请输入数据库root密码:" dbpass
if  [ -z "$dbpass" ] ;then
    echo "请输入数据库root密码!"
    read -p "请输入数据库root密码:" dbpass
else
    echo "数据库root密码: $dbpass"
fi

#替换域名和数据库密码为自定义的内容
sed -i -e 's|www.baidu.com|'$domain'|' nginx.conf
sed -i -e 's|123456|'$dbpass'|' sphinx.conf
sed -i -e 's|123456|'$dbpass'|' simdht_worker.py
sed -i -e 's|123456|'$dbpass'|' manage.py
sed -i -e 's|116.196.82.73|$domain|' manage.py

#修改时区
\cp -rpf /usr/share/zoneinfo/Asia/Chongqing /etc/localtime
#关闭防火墙
systemctl stop firewalld.service  
systemctl disable firewalld.service   
systemctl stop iptables.service  
systemctl disable iptables.service  
#禁用SELinux
setenforce 0  
sed -i s/"SELINUX=enforcing"/"SELINUX=disabled"/g  /etc/selinux/config
#优化内核参数和redis参数
cat << EOF > /etc/sysctl.conf
net.ipv4.tcp_syn_retries = 1
net.ipv4.tcp_synack_retries = 1
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_probes = 3
net.ipv4.tcp_keepalive_intvl =15
net.ipv4.tcp_retries2 = 5
net.ipv4.tcp_fin_timeout = 2
net.ipv4.tcp_max_tw_buckets = 36000
net.ipv4.tcp_tw_recycle = 1
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_max_orphans = 32768
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 16384
net.ipv4.tcp_wmem = 8192 131072 16777216
net.ipv4.tcp_rmem = 32768 131072 16777216
net.ipv4.tcp_mem = 786432 1048576 1572864
net.ipv4.ip_local_port_range = 1024 65000
net.ipv4.ip_conntrack_max = 65536
net.ipv4.netfilter.ip_conntrack_max=65536
net.ipv4.netfilter.ip_conntrack_tcp_timeout_established=180
net.core.somaxconn = 16384
net.core.netdev_max_backlog = 16384
vm.overcommit_memory = 1
net.core.somaxconn = 511
EOF
/sbin/sysctl -p /etc/sysctl.conf
/sbin/sysctl -w net.ipv4.route.flush=1
echo 'ulimit -HSn 65536' >> /etc/rc.local
echo 'ulimit -HSn 65536' >>/root/.bash_profile
echo '*  soft  nofile 65536' >> /etc/security/limits.conf
echo '*  hard  nofile 65536' >> /etc/security/limits.conf
ulimit -HSn 65536
#安装必备组件
yum -y install wget gcc gcc-c++ python-devel mariadb mariadb-devel mariadb-server
yum -y install psmisc net-tools lsof epel-release
yum -y install python-pip
yum -y install redis
#安装各种python库
pip install -r requirements.txt
#如果提示没有pip命令,或者你使用linode的主机,请取消下面4行的注释
#wget -O /etc/yum.repos.d/CentOS-Base.repo http://mirrors.aliyun.com/repo/Centos-7.repo
#wget -qO /etc/yum.repos.d/epel.repo http://mirrors.aliyun.com/repo/epel-7.repo
#yum clean metadata
#yum makecache
mkdir -p uploads  uploads/nvyou  uploads/fanhao
#注册服务
\cp -rpf systemctl/gunicorn.service  systemctl/indexer.service  systemctl/searchd.service /etc/systemd/system
systemctl daemon-reload	
#创建数据库,调整参数
\cp -rpf my.cnf  /etc/my.cnf 
systemctl start  mariadb.service 
echo '无需输入密码,直接回车↓↓↓'
mysqladmin -uroot -p password ${dbpass}
mysql -uroot -p${dbpass} -e "create database IF NOT EXISTS zsky default character set utf8mb4;set global max_allowed_packet = 64*1024*1024;set global max_connections = 100000;" 
#启动数据库和redis
systemctl enable mariadb.service
systemctl start redis.service
systemctl enable redis.service
#数据库建表
python manage.py init_db
#创建管理员,会提示输入管理员用户名和密码,邮箱
python manage.py create_user
#杀死占用80端口的进程
kill -9 $(lsof -i:80|tail -1|awk '"$1"!=""{print $2}')
#配置前端nginx
yum -y install nginx
systemctl start  nginx.service
systemctl enable  nginx.service
\cp -rpf nginx.conf  /etc/nginx/nginx.conf 
nginx -s reload
#启动后端gunicorn+gevent,开启日志并在后台运行
systemctl start gunicorn
systemctl enable gunicorn
#启动爬虫,开启日志并在后台运行
nohup python /root/zsky/simdht_worker.py >/root/zsky/spider.log 2>&1& 
#编译sphinx,启动索引,启动搜索进程
yum -y install git gcc cmake automake g++ mysql-devel
git clone https://github.com/wenguonideshou/sphinx-jieba
cd sphinx-jieba
git submodule update --init --recursive
./configure --prefix=/usr/local/sphinx-jieba
\cp -r cppjieba/include/cppjieba src/ 
\cp -r cppjieba/deps/limonp src/ 
make install
\cp -r cppjieba/dict/* /usr/local/sphinx-jieba/etc/ 
cd /usr/local/sphinx-jieba/
\cp etc/jieba.dict.utf8 etc/xdictjieba.dict.utf8
\cp etc/user.dict.utf8 etc/xdictuser.dict.utf8
\cp etc/hmm_model.utf8 etc/xdicthmm_model.utf8
\cp etc/idf.utf8 etc/xdictidf.utf8
\cp etc/stop_words.utf8 etc/xdictstop_words.utf8
systemctl start indexer	
systemctl enable indexer
systemctl start searchd	
systemctl enable searchd
#设置开机自启动
chmod +x /etc/rc.local
echo "systemctl start  mariadb.service" >> /etc/rc.local
echo "systemctl start  redis.service" >> /etc/rc.local
echo "systemctl start  nginx.service" >> /etc/rc.local
echo "systemctl start  gunicorn.service" >> /etc/rc.local
echo "systemctl start  indexer.service" >> /etc/rc.local
echo "systemctl start  searchd.service" >> /etc/rc.local
echo "nohup python /root/zsky/simdht_worker.py>/root/zsky/spider.log 2>&1&" >> /etc/rc.local
echo "echo never > /sys/kernel/mm/transparent_hugepage/enabled" >> /etc/rc.local
#设置定时任务,每天早上5点进行主索引
yum -y install  vixie-cron crontabs
systemctl start crond.service
systemctl enable crond.service
crontab -l > /tmp/crontab.bak
echo '0 5 * * * /usr/local/sphinx-jieba/bin/indexer -c /root/zsky/sphinx.conf film --rotate&&/usr/local/sphinx-jieba/bin/searchd --config /root/zsky/sphinx.conf' >> /tmp/crontab.bak
crontab /tmp/crontab.bak
#确定是否正确安装
echo '当前进程运行状态:'
pgrep -l nginx
pgrep -l searchd
pgrep -l gunicorn