# zsky
# 使用说明

#### 纸上烤鱼是从浩瀚的DHT网络（UDP）中获取磁力链接（magnet）信息的搜索引擎，主要分为爬虫、网站、数据库、索引，爬虫基于socket、bencode库，网站基于flask库，数据库为mysql，索引为sphinx，请勿用于非法用途
只是一个copy。
使用方法：
```Bash
yum -y install git 
git  clone https://github.com/magrco/zsky.git
cd zsky&&sh zsky.sh
```

安装脚本只支持Centos7+Python2.7环境

主机配置要求：至少1G内存、至少100G硬盘，至少1G SWAP，具有公网IP的国外主机/服务器

> 安装脚本执行过程中会提示输入绑定的域名、数据库密码、管理员用户名、密码、邮箱，输入后耐心等待即可访问 http://域名 

> 后台地址 http://域名/admin 

安装过程中会提示输入数据库密码。

修改simdht_worker.py里的max_node_qsize的大小调节爬取速度（队列大小）

执行  python manage.py init_db     创建表/平滑升级表结构

执行  python manage.py create_user  创建管理员

执行  python manage.py changepassword  修改管理员密码

执行  systemctl start gunicorn  启动网站

执行  systemctl start mariadb  启动数据库

执行  systemctl status mariadb  查看数据库运行状态

执行  systemctl restart mariadb  重新启动数据库

执行  systemctl status gunicorn  查看gunicorn运行状态

执行  systemctl restart gunicorn   重新启动网站

执行  systemctl restart indexer  手动重新索引

执行  systemctl start searchd  开启搜索进程

执行  systemctl status searchd  查看搜索进程运行状态

执行  systemctl restart searchd   重新启动搜索进程

**Q:如何绑定多个域名？**

A：在/etc/nginx/nginx/nginx.conf文件内修改，多个域名用空格隔开，修改完成后执行nginx -s reload生效

**Q：如何修改站点名？**

A：修改manage.py里的常量sitename

**Q：如何修改地图里的域名？**

A：修改manage.py里的常量domain

**Q：如何修改后台地址？**

A：修改manage.py中的以下语句中的url=后面的地址：
admin = Admin(app,name='管理中心',base_template='admin/my_master.html',index_view=MyAdminIndexView(name='首页',template='admin/index.html',url='/fucku'))

**Q：如何屏蔽违禁词**

A：在sensitivewords.txt这个文件里面添加违禁词，一行一个，支持`.*?`等正则符号，添加完成后systemctl restart gunicorn生效

**Q：如何实现远程主机反向代理本机的程序？**

A：修改本机的/etc/systemd/system/gunicorn.service其中的127.0.0.1:8000修改为0.0.0.0:8000然后执行systemctl daemon-reload，然后执行systemctl restart gunicorn，本机不开启nginx，远程主机开启nginx、配置反向代理、绑定域名即可，nginx的配置文件参考程序内的nginx.conf 。

**Q：如何限制/提高爬取速度？**

A：修改simdht_worker.py里的max_node_qsize=后面的数字，越大爬取越快，越小爬取越慢

**Q：如何修改数据库密码？**

A：执行mysqladmin -uroot -p password 123456!@#$%^            //将提示输入当前密码，123456!@#$%^是新密码

**Q：修改数据库密码后怎么修改程序里的配置？**

A：修改manage.py里的mysql+pymysql://root:密码@127.0.0.1、修改manage.py里的DB_PASS、修改simdht_worker.py里的DB_PASS、修改sphinx.conf里的sql_pass

**Q：怎么确定爬虫是在正常运行？**

A：执行 ps -ef|grep -v grep|grep simdht 如果有结果说明爬虫正在运行

**Q：更新manage.py/模板后怎么立即生效？**

A：执行 systemctl restart gunicorn 重启gunicorn

**Q：为什么首页统计的数据小于后台的数据？**

A：在数据量变大后，索引将占用CPU 100%，非常影响用户访问网站，为了最小程度减小此影响 默认设置为每天早上5点更新索引，你想现在更新爬取结果的话，手动执行索引 systemctl restart indexer ，需要注意的是，数据量越大 索引所耗费时间越长

**Q：如何查看索引是否成功？**

A：执行 systemctl status indexer 可以看到索引记录

**Q：觉得索引速度慢，如何加快？**

A：修改sphinx.conf里面的mem_limit = 512M ，根据你的主机的内存使用情况来修改，数值越大索引越快，最大可以设置为2048M

**Q：如何确定搜索进程是否正常运行**

A：执行 systemctl status searchd ，如果是绿色的running说明搜索进程完全正常

**Q：如何备份数据库？**

A：执行 mysqldump -uroot -p zsky>/root/zsky.sql  导出数据库        //将提示输入当前密码，数据库导出后存在/root/zsky.sql

**Q：数据库备份后，现在重新安装了程序，如何导入旧数据？**

A：执行 mysql -uroot -p zsky</root/zsky.sql       //假设你的旧数据库文件是/root/zsky.sql，将提示输入当前密码，输入后耐心等待

**Q：如何迁移到新主机？**

A：备份数据库（方法见上面）→ 程序拷贝到新主机 → 安装程序 → 导入数据库（方法见上面）→ 重新索引

**Q：我以前使用的搜片大师/手撕包菜，可以迁移过来吗？**

A：程序在开发之初就已经考虑到从这些程序迁移过来的问题，所以你不用担心，完全可以无缝迁移。如果有需求，请加群联系作者付费为你提供服务

**Q：网站经常收到版权投诉，有没有好的解决办法？**

A：除了删除投诉的影片数据外，你可以使用前端Nginx、后端gunicorn+爬虫+数据库+索引在不同主机上的模式，甚至多前端模式，这样 即使前端被主机商强行封机，也能保证后端数据的安全。如果有需求，请加群联系作者付费为你提供服务
欢迎访问：http://dht.im 更多技术分享：http:www.magrco.com
