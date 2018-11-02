#!/usr/bin/env python
# encoding: utf-8
"""
磁力搜索meta信息入库程序
2017.7 我本戏子
"""


import socket
import hashlib
import os
import SimpleXMLRPCServer
import time
import datetime
import traceback
import sys
import json
import threading
from hashlib import sha1
from random import randint
from socket import inet_ntoa
from collections import deque
from Queue import Queue
import MySQLdb
from DBUtils.PooledDB import PooledDB
import math
from struct import pack, unpack
from threading import Timer, Thread
from time import sleep, time
from bencode import bencode, bdecode
import binascii
import random

try:
    import libtorrent as lt
except:
    lt = None
    print sys.exc_info()[1]


DB_NAME = 'zsky'
DB_HOST = '127.0.0.1'
DB_USER = 'root'
DB_PASS = '123456'
BOOTSTRAP_NODES = (
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881)
)
TID_LENGTH = 2
RE_JOIN_DHT_INTERVAL = 3
TOKEN_LENGTH = 2
BT_PROTOCOL = "BitTorrent protocol"
BT_MSG_ID = 20
EXT_HANDSHAKE_ID = 0


def get_extension(name):
    return os.path.splitext(name)[1]

def get_category(ext):
    ext = ext + '.'
    cats = {
        u'影视': '.avi.mp4.rmvb.m2ts.wmv.mkv.flv.qmv.rm.mov.vob.asf.3gp.mpg.mpeg.m4v.f4v.',
        u'图像': '.jpg.bmp.jpeg.png.gif.tiff.',
        u'文档书籍': '.pdf.isz.chm.txt.epub.bc!.doc.ppt.',
        u'音乐': '.mp3.ape.wav.dts.mdf.flac.',
        u'压缩文件': '.zip.rar.7z.tar.gz.iso.dmg.pkg.',
        u'安装包': '.exe.app.msi.apk.'
    }
    for k, v in cats.iteritems():
        if ext in v:
            return k
    return u'其他'

def get_detail(y):
    if y.get('files'):
        y['files'] = [z for z in y['files'] if not z['path'].startswith('_')]
    else:
        y['files'] = [{'path': y['name'], 'length': y['length']}]
    y['files'].sort(key=lambda z:z['length'], reverse=True)
    bigfname = y['files'][0]['path']
    ext = get_extension(bigfname).lower()
    y['category'] = get_category(ext)
    y['extension'] = ext
    
def random_id():
    hash = sha1()
    hash.update(entropy(20))
    return hash.digest()

def send_packet(the_socket, msg):
    the_socket.send(msg)

def send_message(the_socket, msg):
    msg_len = pack(">I", len(msg))
    send_packet(the_socket, msg_len + msg)

def send_handshake(the_socket, infohash):
    bt_header = chr(len(BT_PROTOCOL)) + BT_PROTOCOL
    ext_bytes = "\x00\x00\x00\x00\x00\x10\x00\x00"
    peer_id = random_id()
    packet = bt_header + ext_bytes + infohash + peer_id

    send_packet(the_socket, packet)

def check_handshake(packet, self_infohash):
    try:
        bt_header_len, packet = ord(packet[:1]), packet[1:]
        if bt_header_len != len(BT_PROTOCOL):
            return False
    except TypeError:
        return False

    bt_header, packet = packet[:bt_header_len], packet[bt_header_len:]
    if bt_header != BT_PROTOCOL:
        return False

    packet = packet[8:]
    infohash = packet[:20]
    if infohash != self_infohash:
        return False

    return True

def send_ext_handshake(the_socket):
    msg = chr(BT_MSG_ID) + chr(EXT_HANDSHAKE_ID) + bencode({"m":{"ut_metadata": 1}})
    send_message(the_socket, msg)

def request_metadata(the_socket, ut_metadata, piece):
    """bep_0009"""
    msg = chr(BT_MSG_ID) + chr(ut_metadata) + bencode({"msg_type": 0, "piece": piece})
    send_message(the_socket, msg)

def get_ut_metadata(data):
    ut_metadata = "_metadata"
    index = data.index(ut_metadata)+len(ut_metadata) + 1
    return int(data[index])

def get_metadata_size(data):
    metadata_size = "metadata_size"
    start = data.index(metadata_size) + len(metadata_size) + 1
    data = data[start:]
    return int(data[:data.index("e")])

def recvall(the_socket, timeout=5):
    the_socket.setblocking(0)
    total_data = []
    data = ""
    begin = time()

    while True:
        sleep(0.05)
        if total_data and time()-begin > timeout:
            break
        elif time()-begin > timeout*2:
            break
        try:
            data = the_socket.recv(1024)
            if data:
                total_data.append(data)
                begin = time()
        except Exception:
            pass
    return "".join(total_data)
    
def entropy(length):
    return "".join(chr(randint(0, 255)) for _ in xrange(length))


def random_id():
    h = sha1()
    h.update(entropy(20))
    return h.digest()


def decode_nodes(nodes):
    n = []
    length = len(nodes)
    if (length % 26) != 0:
        return n

    for i in range(0, length, 26):
        nid = nodes[i:i+20]
        ip = inet_ntoa(nodes[i+20:i+24])
        port = unpack("!H", nodes[i+24:i+26])[0]
        n.append((nid, ip, port))

    return n


def timer(t, f):
    Timer(t, f).start()


def get_neighbor(target, nid, end=10):
    return target[:end]+nid[end:]


class KNode(object):

    def __init__(self, nid, ip, port):
        self.nid = nid
        self.ip = ip
        self.port = port


class DHTClient(Thread):

    def __init__(self, max_node_qsize):
        Thread.__init__(self)
        self.setDaemon(True)
        self.max_node_qsize = max_node_qsize
        self.nid = random_id()
        self.nodes = deque(maxlen=max_node_qsize)

    def send_krpc(self, msg, address):
        try:
            self.ufd.sendto(bencode(msg), address)
        except Exception:
            pass

    def send_find_node(self, address, nid=None):
        nid = get_neighbor(nid, self.nid) if nid else self.nid
        tid = entropy(TID_LENGTH)
        msg = {
            "t": tid,
            "y": "q",
            "q": "find_node",
            "a": {
                "id": nid,
                "target": random_id()
            }
        }
        self.send_krpc(msg, address)

    def join_DHT(self):
        for address in BOOTSTRAP_NODES:
            self.send_find_node(address)

    def re_join_DHT(self):
        if len(self.nodes) == 0:
            self.join_DHT()
        timer(RE_JOIN_DHT_INTERVAL, self.re_join_DHT)

    def auto_send_find_node(self):
        wait = 1.0 / self.max_node_qsize
        while True:
            try:
                node = self.nodes.popleft()
                self.send_find_node((node.ip, node.port), node.nid)
            except IndexError:
                pass
            try:
                sleep(wait)
            except KeyboardInterrupt:
                os._exit(0)

    def process_find_node_response(self, msg, address):
        nodes = decode_nodes(msg["r"]["nodes"])
        for node in nodes:
            (nid, ip, port) = node
            if len(nid) != 20: continue
            if ip == self.bind_ip: continue
            n = KNode(nid, ip, port)
            self.nodes.append(n)


class DHTServer(DHTClient):

    def __init__(self, master, bind_ip, bind_port, max_node_qsize):
        DHTClient.__init__(self, max_node_qsize)

        self.master = master
        self.bind_ip = bind_ip
        self.bind_port = bind_port

        self.process_request_actions = {
            "get_peers": self.on_get_peers_request,
            "announce_peer": self.on_announce_peer_request,
        }

        self.ufd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.ufd.bind((self.bind_ip, self.bind_port))

        timer(RE_JOIN_DHT_INTERVAL, self.re_join_DHT)


    def run(self):
        self.re_join_DHT()
        while True:
            try:
                (data, address) = self.ufd.recvfrom(65536)
                msg = bdecode(data)
                self.on_message(msg, address)
            except Exception:
                pass

    def on_message(self, msg, address):
        try:
            if msg["y"] == "r":
                if msg["r"].has_key("nodes"):
                    self.process_find_node_response(msg, address)
            elif msg["y"] == "q":
                try:
                    self.process_request_actions[msg["q"]](msg, address)
                except KeyError:
                    self.play_dead(msg, address)
        except KeyError:
            pass

    def on_get_peers_request(self, msg, address):
        try:
            infohash = msg["a"]["info_hash"]
            tid = msg["t"]
            nid = msg["a"]["id"]
            token = infohash[:TOKEN_LENGTH]
            msg = {
                "t": tid,
                "y": "r",
                "r": {
                    "id": get_neighbor(infohash, self.nid),
                    "nodes": "",
                    "token": token
                }
            }
            self.master.log_hash(infohash, address)
            self.send_krpc(msg, address)
        except KeyError:
            pass

    def on_announce_peer_request(self, msg, address):
        try:
            infohash = msg["a"]["info_hash"]
            token = msg["a"]["token"]
            nid = msg["a"]["id"]
            tid = msg["t"]

            if infohash[:TOKEN_LENGTH] == token:
                if msg["a"].has_key("implied_port ") and msg["a"]["implied_port "] != 0:
                    port = address[1]
                else:
                    port = msg["a"]["port"]
                self.master.log_announce(infohash, (address[0], port))
        except Exception:
            print 'error'
            pass
        finally:
            self.ok(msg, address)

    def play_dead(self, msg, address):
        try:
            tid = msg["t"]
            msg = {
                "t": tid,
                "y": "e",
                "e": [202, "Server Error"]
            }
            self.send_krpc(msg, address)
        except KeyError:
            pass

    def ok(self, msg, address):
        try:
            tid = msg["t"]
            nid = msg["a"]["id"]
            msg = {
                "t": tid,
                "y": "r",
                "r": {
                    "id": get_neighbor(nid, self.nid)
                }
            }
            self.send_krpc(msg, address)
        except KeyError:
            pass


class Master(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.setDaemon(True)
        self.queue = Queue(maxsize = 1000000)
        self.metadata_queue = Queue(maxsize = 1000000)
        self.pool = PooledDB(MySQLdb,50,host=DB_HOST,user=DB_USER,passwd=DB_PASS,db=DB_NAME,port=3306,charset="utf8mb4") #50为连接池里的最少连接数
        self.dbconn = self.pool.connection()
        self.dbcurr = self.dbconn.cursor()
        self.dbcurr.execute('SET NAMES utf8mb4')
        self.n_reqs = self.n_valid = self.n_new = 0
        self.n_downloading_lt = self.n_downloading_pt = 0
        self.visited = set()

    def got_torrent(self):
        utcnow = datetime.datetime.utcnow()
        binhash, address, data, dtype, start_time = self.metadata_queue.get()
        if dtype == 'pt':
            self.n_downloading_pt -= 1
        elif dtype == 'lt':
            self.n_downloading_lt -= 1
        if not data:
            return
        self.n_valid += 1
        
        try:
            info = self.parse_torrent(data)
            if not info:
                return
        except:
            traceback.print_exc()
            return
        info_hash = binhash.encode('hex')
        info['info_hash'] = info_hash

        info['tagged'] = False
        info['classified'] = False
        info['requests'] = 1
        info['last_seen'] = utcnow + datetime.timedelta(hours=8)
        info['source_ip'] = address[0]

        if info.get('files'):
            files = [z for z in info['files'] if not z['path'].startswith('_')]
            if not files:
                files = info['files']
        else:
            files = [{'path': info['name'], 'length': info['length']}]
            
        files.sort(key=lambda z:z['length'], reverse=True)
        bigfname = files[0]['path']
        info['extension'] = get_extension(bigfname).lower()
        info['category'] = get_category(info['extension'])

        if 'files' in info:
            try:
                self.dbcurr.execute('INSERT IGNORE INTO search_filelist VALUES(%s, %s)', (info['info_hash'], json.dumps(files)))
            except:
                print self.name, 'insert search_filelist error', sys.exc_info()[1]
            del files

        try:
            #print '\n', 'Saved', info['info_hash'], info['name'], (time.time()-start_time), 's', address[0], geoip.country_name_by_addr(address[0]),
            self.dbcurr.execute('INSERT IGNORE INTO search_hash(info_hash,category,data_hash,name,extension,classified,source_ip,tagged,length,create_time,last_seen,requests,comment,creator) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(info['info_hash'], info['category'], info['data_hash'], info['name'], info['extension'], info['classified'], info['source_ip'], info['tagged'], info['length'], info['create_time'], info['last_seen'], info['requests'], info.get('comment',''), info.get('creator','')))
            self.dbcurr.connection.commit()
            self.n_new += 1
            print '\n', (datetime.datetime.utcnow()+ datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"), info['info_hash'], address[0], 'saved!'
        except:
            print self.name, 'save search_hash error', info
            traceback.print_exc()
            return



    def run(self):
        self.name = threading.currentThread().getName()
        print self.name, 'started'
        while True:
            while self.metadata_queue.qsize() > 0:
                self.got_torrent()
            address, binhash, dtype = self.queue.get()
            if binhash in self.visited:
                continue
            if len(self.visited) > 100000:
                self.visited = set()
            self.visited.add(binhash)

            self.n_reqs += 1
            info_hash = binhash.encode('hex')

            utcnow = datetime.datetime.utcnow()
            date = (utcnow + datetime.timedelta(hours=8))
            date = datetime.datetime(date.year, date.month, date.day, date.hour, date.minute, date.second)

            # 检查infohash是否存在
            self.dbcurr.execute('SELECT id FROM search_hash WHERE info_hash=%s', (info_hash,))
            y = self.dbcurr.fetchone()
            if y:
                self.n_valid += 1
                # 更新最近发现时间、请求数
                self.dbcurr.execute('UPDATE search_hash SET last_seen=%s, requests=requests+1 WHERE info_hash=%s', (date, info_hash))
            else:
                if dtype == 'pt':
                    t = threading.Thread(target=self.download_metadata, args=(address, binhash, self.metadata_queue))
                    t.setDaemon(True)
                    t.start()
                    self.n_downloading_pt += 1
                elif dtype == 'lt' :
                    t = threading.Thread(target=self.ltdownload_metadata, args=(address, binhash, self.metadata_queue))
                    t.setDaemon(True)
                    t.start()
                    self.n_downloading_lt += 1

            if self.n_reqs >= 1000:
                self.dbcurr.execute('INSERT INTO search_statusreport(date,new_hashes,total_requests, valid_requests)  VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE ' +
                    'total_requests=total_requests+%s, valid_requests=valid_requests+%s, new_hashes=new_hashes+%s',
                    (date, self.n_new, self.n_reqs, self.n_valid, self.n_reqs, self.n_valid, self.n_new))
                self.dbconn.commit()
                #print '\n', time.ctime(), 'n_reqs', self.n_reqs, 'n_valid', self.n_valid, 'n_new', self.n_new, 'n_queue', self.queue.qsize(), 
                #print 'n_d_pt', self.n_downloading_pt, 'n_d_lt', self.n_downloading_lt, 
                self.n_reqs = self.n_valid = self.n_new = 0

    def decode(self, s):
        if type(s) is list:
            s = ';'.join(s)
        u = s
        for x in (self.encoding, 'utf8', 'gbk', 'big5'):
            try:
                u = s.decode(x)
                return u
            except:
                pass
        return s.decode(self.encoding, 'ignore')

    def decode_utf8(self, d, i):
        if i+'.utf-8' in d:
            return d[i+'.utf-8'].decode('utf8')
        return self.decode(d[i])

    def parse_torrent(self, data):
        info = {}
        self.encoding = 'utf8'
        try:
            torrent = bdecode(data)
            if not torrent.get('name'):
                return None
        except:
            return None
        try:
            info['create_time'] = datetime.datetime.fromtimestamp(float(torrent['creation date'])) + datetime.timedelta(hours=8)
        except:
            info['create_time'] = datetime.datetime.utcnow() + datetime.timedelta(hours=8)

        if torrent.get('encoding'):
            self.encoding = torrent['encoding']
        if torrent.get('announce'):
            info['announce'] = self.decode_utf8(torrent, 'announce')
        if torrent.get('comment'):
            info['comment'] = self.decode_utf8(torrent, 'comment')[:200]
        if torrent.get('publisher-url'):
            info['publisher-url'] = self.decode_utf8(torrent, 'publisher-url')
        if torrent.get('publisher'):
            info['publisher'] = self.decode_utf8(torrent, 'publisher')
        if torrent.get('created by'):
            info['creator'] = self.decode_utf8(torrent, 'created by')[:15]

        if 'info' in torrent:
            detail = torrent['info'] 
        else:
            detail = torrent
        info['name'] = self.decode_utf8(detail, 'name')
        if 'files' in detail:
            info['files'] = []
            for x in detail['files']:
                if 'path.utf-8' in x:
                    v = {'path': self.decode('/'.join(x['path.utf-8'])), 'length': x['length']}
                else:
                    v = {'path': self.decode('/'.join(x['path'])), 'length': x['length']}
                if 'filehash' in x:
                    v['filehash'] = x['filehash'].encode('hex')
                info['files'].append(v)
            info['length'] = sum([x['length'] for x in info['files']])
        else:
            info['length'] = detail['length']
        info['data_hash'] = hashlib.md5(detail['pieces']).hexdigest()
        if 'profiles' in detail:
            info['profiles'] = detail['profiles']
        return info
    threading.stack_size(200*1024)
    socket.setdefaulttimeout(30)

    def log_announce(self, binhash, address=None):
        self.queue.put([address, binhash, 'pt'])

    def log_hash(self, binhash, address=None):
        if not lt:
            return
        if self.n_downloading_lt :
            self.queue.put([address, binhash, 'lt'])

    def fetch_torrent(session, ih, timeout):
        name = ih.upper()
        url = 'magnet:?xt=urn:btih:%s' % (name,)
        data = ''
        params = {
            'save_path': '/tmp/downloads/',
            'storage_mode': lt.storage_mode_t(2),
            'paused': False,
            'auto_managed': False,
            'duplicate_is_error': True}
        try:
            handle = lt.add_magnet_uri(session, url, params)
        except:
            return None
        status = session.status()
        #print 'downloading metadata:', url
        handle.set_sequential_download(1)
        meta = None
        down_time = time.time()
        down_path = None
        for i in xrange(0, timeout):
            if handle.has_metadata():
                info = handle.get_torrent_info()
                down_path = '/tmp/downloads/%s' % info.name()
                #print 'status', 'p', status.num_peers, 'g', status.dht_global_nodes, 'ts', status.dht_torrents, 'u', status.total_upload, 'd', status.total_download
                meta = info.metadata()
                break
            time.sleep(1)
        if down_path and os.path.exists(down_path):
            os.system('rm -rf "%s"' % down_path)
        session.remove_torrent(handle)
        return meta

    def ltdownload_metadata(address, binhash, metadata_queue, timeout=40):
        metadata = None
        start_time = time.time()
        try:
            session = lt.session()
            r = random.randrange(10000, 50000)
            session.listen_on(r, r+10)
            session.add_dht_router('router.bittorrent.com',6881)
            session.add_dht_router('router.utorrent.com',6881)
            session.add_dht_router('dht.transmission.com',6881)
            session.add_dht_router('127.0.0.1',6881)
            session.start_dht()
            metadata = fetch_torrent(session, binhash.encode('hex'), timeout)
            session = None
        except:
            traceback.print_exc()
        finally:
            metadata_queue.put((binhash, address, metadata, 'lt', start_time))

    def download_metadata(self, address, infohash, metadata_queue, timeout=5):
        metadata = None
        start_time = time()
        try:
            the_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            the_socket.settimeout(timeout)
            the_socket.connect(address)

            # handshake
            send_handshake(the_socket, infohash)
            packet = the_socket.recv(4096)

            # handshake error
            if not check_handshake(packet, infohash):
                return

            # ext handshake
            send_ext_handshake(the_socket)
            packet = the_socket.recv(4096)

            # get ut_metadata and metadata_size
            ut_metadata, metadata_size = get_ut_metadata(packet), get_metadata_size(packet)
            #print 'ut_metadata_size: ', metadata_size

            # request each piece of metadata
            metadata = []
            for piece in range(int(math.ceil(metadata_size/(16.0*1024)))):
                request_metadata(the_socket, ut_metadata, piece)
                packet = recvall(the_socket, timeout) #the_socket.recv(1024*17) #
                metadata.append(packet[packet.index("ee")+2:])

            metadata = "".join(metadata)
            #print 'Fetched', bdecode(metadata)["name"], "size: ", len(metadata)

        except socket.timeout:
            pass
        except Exception, e:
            pass #print e

        finally:
            the_socket.close()
            metadata_queue.put((infohash, address, metadata, 'pt', start_time))


def announce(info_hash, address):
    binhash = info_hash.decode('hex')
    master.log_announce(binhash, address)
    return 'ok'


def rpc_server():
    rpcserver = SimpleXMLRPCServer.SimpleXMLRPCServer(('localhost', 8004), logRequests=False)
    rpcserver.register_function(announce, 'announce')
    print 'Starting xml rpc server...'
    rpcserver.serve_forever()


if __name__ == "__main__":
    # max_node_qsize bigger, bandwith bigger, spped higher
    master = Master()
    master.start()

    rpcthread = threading.Thread(target=rpc_server)
    rpcthread.setDaemon(True)
    rpcthread.start()

    dht = DHTServer(master, "0.0.0.0", 6881, max_node_qsize=2000)
    dht.start()
    dht.auto_send_find_node()
