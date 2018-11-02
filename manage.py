#encoding:utf-8
#我本戏子2017.7
from __future__ import print_function
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import redis
import re
import base64
import json
import codecs
import time
import os
import datetime
from flask import Flask,request,render_template,session,g,url_for,redirect,flash,current_app,jsonify,send_from_directory
from flask_login import LoginManager,UserMixin,current_user,login_required,login_user,logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Date, cast, func
from flask_script import Manager, Shell
from flask_migrate import Migrate, MigrateCommand
from flask_wtf import FlaskForm
from wtforms import StringField,PasswordField,SubmitField,BooleanField,TextField
from wtforms.validators import DataRequired,Length,EqualTo,ValidationError
from flask_babelex import Babel,gettext
from flask_admin import helpers, AdminIndexView, Admin, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.contrib.fileadmin import FileAdmin
from flask_admin.form.upload import ImageUploadField
from getpass import getpass
from flask_caching import Cache
from werkzeug.security import generate_password_hash,check_password_hash
import jieba
import jieba.analyse
import MySQLdb
import MySQLdb.cursors


file_path = os.path.join(os.path.dirname(__file__), 'uploads')
# Initialize Flask and set some config values
app = Flask(__name__)
app.config['DEBUG']=True
app.config['SECRET_KEY'] = 'super-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:123456@127.0.0.1:3306/zsky'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
app.config['SQLALCHEMY_POOL_SIZE']=5000
db = SQLAlchemy(app)
manager = Manager(app)
migrate = Migrate(app, db)
babel = Babel(app)
app.config['BABEL_DEFAULT_LOCALE'] = 'zh_CN'
loginmanager=LoginManager()
loginmanager.init_app(app)
loginmanager.session_protection='strong'
loginmanager.login_view='login'
loginmanager.login_message = "请先登录！"
cache = Cache(app,config = {
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': '127.0.0.1',
    'CACHE_REDIS_PORT': 6379,
    'CACHE_REDIS_DB': '',
    'CACHE_REDIS_PASSWORD': ''
})
cache.init_app(app)


DB_HOST='127.0.0.1'
DB_NAME_MYSQL='zsky'
DB_PORT_MYSQL=3306
DB_NAME_SPHINX='film'
DB_PORT_SPHINX=9306
DB_USER='root'
DB_PASS='123456'
DB_CHARSET='utf8mb4'

sitename="纸上烤鱼"
#站点名
domain="http://116.196.82.73/"
#sitemap里的域名

class LoginForm(FlaskForm):
    name=StringField('用户名',validators=[DataRequired(),Length(1,32)])
    password=PasswordField('密码',validators=[DataRequired(),Length(1,20)])
    def get_user(self):
        return db.session.query(User).filter_by(name=self.name.data).first()


class SearchForm(FlaskForm):
    search = StringField(validators = [DataRequired(message= '请输入关键字')],render_kw={"placeholder":"搜索电影,软件,图片,资料,番号...."})
    submit = SubmitField('搜索')


class Search_Filelist(db.Model):
    """ 文件列表 """
    __tablename__ = 'search_filelist'
    info_hash = db.Column(db.String(40), primary_key=True,nullable=False)
    file_list = db.Column(db.Text,nullable=False)


class Search_Hash(db.Model,UserMixin):
    """ Hash列表 """
    __tablename__ = 'search_hash'
    id = db.Column(db.Integer,primary_key=True,nullable=False,autoincrement=True)
    info_hash = db.Column(db.String(40),unique=True)
    category = db.Column(db.String(20))
    data_hash = db.Column(db.String(32))
    name = db.Column(db.String(200),index=True)
    extension = db.Column(db.String(20))
    classified = db.Column(db.Boolean())
    source_ip = db.Column(db.String(20))
    tagged = db.Column(db.Boolean(),default=False)
    length = db.Column(db.BigInteger)
    create_time = db.Column(db.DateTime,default=datetime.datetime.now)
    last_seen = db.Column(db.DateTime,default=datetime.datetime.now)
    requests = db.Column(db.Integer)
    comment = db.Column(db.String(100))
    creator = db.Column(db.String(20))

class Search_Keywords(db.Model):
    """ 首页推荐 """
    __tablename__ = 'search_keywords'
    id = db.Column(db.Integer,primary_key=True,nullable=False,autoincrement=True)
    keyword = db.Column(db.String(20),nullable=False,unique=True)
    order = db.Column(db.Integer,nullable=False)
    pic = db.Column(db.String(100),nullable=False)
    score = db.Column(db.String(10),nullable=False)

class Search_Tags(db.Model):
    """ 搜索记录 """
    __tablename__ = 'search_tags'
    id = db.Column(db.Integer,primary_key=True,nullable=False,autoincrement=True)
    tag = db.Column(db.String(50),nullable=False,unique=True)

class Search_Statusreport(db.Model):
    """ 爬取统计 """
    __tablename__ = 'search_statusreport'
    id = db.Column(db.Integer, primary_key=True,nullable=False,autoincrement=True)
    date = db.Column(db.DateTime,nullable=False,default=datetime.datetime.now)
    new_hashes = db.Column(db.Integer,nullable=False)
    total_requests = db.Column(db.Integer,nullable=False)
    valid_requests = db.Column(db.Integer,nullable=False)
    

class User(db.Model, UserMixin):
    """ 用户表 """
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    email = db.Column(db.String(50),nullable=False)
    name = db.Column(db.String(50),unique=True,nullable=False)
    password = db.Column(db.String(200),nullable=False)
    def is_authenticated(self):
        return True
    def is_active(self):
        return True
    def is_anonymous(self):
        return False
        return self.id
    def __unicode__(self):
        return self.name

def make_shell_context():
    return dict(app=app, db=db, Search_Filelist=Search_Filelist, Search_Hash=Search_Hash, Search_Keywords=Search_Keywords,Search_Tags=Search_Tags, Search_Statusreport=Search_Statusreport, User=User)
manager.add_command("shell", Shell(make_context=make_shell_context))
manager.add_command('db', MigrateCommand)

@loginmanager.user_loader
def load_user(id):
    return User.query.get(int(id))


def make_cache_key(*args, **kwargs):
    path = request.path
    args = str(hash(frozenset(request.args.items())))
    return (path + args).encode('utf-8')

def replace_keyword_filter(str, old, new):
    return re.sub(r'(?i)('+old+')', new, str)
app.add_template_filter(replace_keyword_filter,'replace')

def filelist_filter(info_hash):
    try:
        return json.loads(Search_Filelist.query.filter_by(info_hash=info_hash).first().file_list)
    except:
        return [{
       'path':Search_Hash.query.filter_by(info_hash=info_hash).first().name, 
       'length':Search_Hash.query.filter_by(info_hash=info_hash).first().length
       }]
app.add_template_filter(filelist_filter,'filelist')


def todate_filter(s):
    return datetime.datetime.fromtimestamp(int(s)).strftime('%Y-%m-%d')
app.add_template_filter(todate_filter,'todate')


def tothunder_filter(magnet):
    return base64.b64encode('AA'+magnet+'ZZ')
app.add_template_filter(tothunder_filter,'tothunder')

def sphinx_conn():
    conn = MySQLdb.connect(host=DB_HOST, port=DB_PORT_SPHINX, user=DB_USER, passwd=DB_PASS, db=DB_NAME_SPHINX,
                           charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
    curr = conn.cursor()
    return (conn,curr)
    
def sphinx_close(curr,conn):
    curr.close()
    conn.close()

thisweek = int(time.mktime(datetime.datetime.now().timetuple())) - 86400 * 7

@app.route('/weekhot.html', methods=['GET', 'POST'])
@cache.cached(timeout=60*5,key_prefix=make_cache_key)
def weekhot():
    conn,curr = sphinx_conn()
    weekhotsql = 'SELECT * FROM film WHERE create_time>%s order by requests desc limit 50'
    curr.execute(weekhotsql, [thisweek])
    weekhot = curr.fetchall()
    sphinx_close(curr,conn)
    form = SearchForm()
    return render_template('weekhot.html', form=form, weekhot=weekhot, sitename=sitename)


@app.route('/new.html', methods=['GET', 'POST'])
@cache.cached(timeout=60*5,key_prefix=make_cache_key)
def new():
    conn,curr = sphinx_conn()
    newestsql = 'SELECT * FROM film order by create_time desc limit 50'
    curr.execute(newestsql)
    newest = curr.fetchall()
    sphinx_close(curr,conn)
    form = SearchForm()
    return render_template('new.html', form=form, newest=newest, sitename=sitename)

@app.route('/tag.html', methods=['GET', 'POST'])
# @cache.cached(timeout=60*60,key_prefix=make_cache_key)
def tag():
    tags = Search_Tags.query.order_by(Search_Tags.id.desc()).limit(160)
    form = SearchForm()
    return render_template('tag.html', form=form, tags=tags, sitename=sitename)

    
@app.route('/',methods=['GET','POST'])
#@cache.cached(60*60*24)
def index():
    conn,curr = sphinx_conn()
    totalsql = 'select count(*) from film'
    curr.execute(totalsql)
    totalcounts = curr.fetchall()
    total = int(totalcounts[0]['count(*)'])
    sphinx_close(curr,conn)
    keywords=Search_Keywords.query.order_by(Search_Keywords.order).limit(6)
    form=SearchForm()
    today = db.session.query(func.sum(Search_Statusreport.new_hashes)).filter(cast(Search_Statusreport.date, Date) == datetime.date.today()).scalar()
    return render_template('index.html',form=form,keywords=keywords,total=total,today=today,sitename=sitename)

def sensitivewords():
    sensitivewordslist = []
    sensitivefile = os.path.join(os.path.dirname(__file__), 'sensitivewords.txt')
    with open(sensitivefile, 'rb') as f:
        for line in f:
            word = re.compile(line.rstrip('\r\n\t').decode('utf-8'))
            sensitivewordslist.append(word)
    return  sensitivewordslist

@app.route('/search',methods=['GET','POST'])
def search():
    form=SearchForm()
    if not form.search.data or re.match(r"^['`=\(\)\|\!\-\@\~\"\&\/\\\^\$].*?", form.search.data) or re.match(r".*?['`=\(\)\|\!\-\@\~\"\&\/\\\^\$]$", form.search.data):
        return redirect(url_for('index'))
    query = re.sub(r"(['`=\(\)|\!@~\"&/\\\^\$])", r"", form.search.data)
    query = re.sub(r"(-+)", r"-", query)
    sensitivewordslist=sensitivewords()
    for word in sensitivewordslist:
        if word.search(query):
            return redirect(url_for('index'))
    return redirect(url_for('search_results',query=query,page=1))


@app.route('/main-search-kw-<query>-<int:page>.html',methods=['GET','POST'])
#@cache.cached(timeout=60*60,key_prefix=make_cache_key)
def search_results(query,page=1):
    sensitivewordslist=sensitivewords()
    for word in sensitivewordslist:
        if word.search(query):
            return redirect(url_for('index'))
    connzsky = MySQLdb.connect(host=DB_HOST,port=DB_PORT_MYSQL,user=DB_USER,password=DB_PASS,db=DB_NAME_MYSQL,charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
    currzsky = connzsky.cursor()
    taginsertsql = 'REPLACE INTO search_tags(tag) VALUES(%s)'
    currzsky.execute(taginsertsql,[query])
    connzsky.commit()
    currzsky.close()
    connzsky.close()
    conn,curr = sphinx_conn()
    querysql='SELECT * FROM film WHERE MATCH(%s) limit %s,20 OPTION max_matches=50000'
    curr.execute(querysql,[query,(page-1)*20])
    result=curr.fetchall()
    #countsql='SELECT COUNT(*)  FROM film WHERE MATCH(%s)'
    countsql='SHOW META'
    curr.execute(countsql)
    resultcounts=curr.fetchall()
    counts=int(resultcounts[0]['Value'])
    taketime=float(resultcounts[2]['Value'])
    sphinx_close(curr,conn)
    pages=(counts+19)/20
    tags=Search_Tags.query.order_by(Search_Tags.id.desc()).limit(50)
    form=SearchForm()
    form.search.data=query
    return render_template('list.html',form=form,query=query,pages=pages,page=page,hashs=result,counts=counts,taketime=taketime,tags=tags,sitename=sitename)


@app.route('/main-search-kw-<query>-length-<int:page>.html',methods=['GET','POST'])
#@cache.cached(timeout=60*60,key_prefix=make_cache_key)
def search_results_bylength(query,page=1):
    sensitivewordslist=sensitivewords()
    for word in sensitivewordslist:
        if word.search(query):
            return redirect(url_for('index'))
    connzsky = MySQLdb.connect(host=DB_HOST,port=DB_PORT_MYSQL,user=DB_USER,password=DB_PASS,db=DB_NAME_MYSQL,charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
    currzsky = connzsky.cursor()
    taginsertsql = 'REPLACE INTO search_tags(tag) VALUES(%s)'
    currzsky.execute(taginsertsql,[query])
    connzsky.commit()
    currzsky.close()
    connzsky.close()
    conn,curr = sphinx_conn()
    querysql='SELECT * FROM film WHERE MATCH(%s) ORDER BY length DESC limit %s,20 OPTION max_matches=50000'
    curr.execute(querysql,[query,(page-1)*20])
    result=curr.fetchall()
    #countsql='SELECT COUNT(*)  FROM film WHERE MATCH(%s)'
    countsql='SHOW META'
    curr.execute(countsql)
    resultcounts=curr.fetchall()
    counts=int(resultcounts[0]['Value'])
    taketime=float(resultcounts[2]['Value'])
    sphinx_close(curr,conn)
    pages=(counts+19)/20
    tags=Search_Tags.query.order_by(Search_Tags.id.desc()).limit(50)
    form=SearchForm()
    form.search.data=query
    return render_template('list_bylength.html',form=form,query=query,pages=pages,page=page,hashs=result,counts=counts,taketime=taketime,tags=tags,sitename=sitename)


@app.route('/main-search-kw-<query>-time-<int:page>.html',methods=['GET','POST'])
#@cache.cached(timeout=60*60,key_prefix=make_cache_key)
def search_results_bycreate_time(query,page=1):
    sensitivewordslist=sensitivewords()
    for word in sensitivewordslist:
        if word.search(query):
            return redirect(url_for('index'))
    connzsky = MySQLdb.connect(host=DB_HOST,port=DB_PORT_MYSQL,user=DB_USER,password=DB_PASS,db=DB_NAME_MYSQL,charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
    currzsky = connzsky.cursor()
    taginsertsql = 'REPLACE INTO search_tags(tag) VALUES(%s)'
    currzsky.execute(taginsertsql,[query])
    connzsky.commit()
    currzsky.close()
    connzsky.close()
    conn,curr = sphinx_conn()
    querysql='SELECT * FROM film WHERE MATCH(%s) ORDER BY create_time DESC limit %s,20 OPTION max_matches=50000'
    curr.execute(querysql,[query,(page-1)*20])
    result=curr.fetchall()
    #countsql='SELECT COUNT(*)  FROM film WHERE MATCH(%s)'
    countsql='SHOW META'
    curr.execute(countsql)
    resultcounts=curr.fetchall()
    counts=int(resultcounts[0]['Value'])
    taketime=float(resultcounts[2]['Value'])
    sphinx_close(curr,conn)
    pages=(counts+19)/20
    tags=Search_Tags.query.order_by(Search_Tags.id.desc()).limit(50)
    form=SearchForm()
    form.search.data=query
    return render_template('list_bycreate_time.html',form=form,query=query,pages=pages,page=page,hashs=result,counts=counts,taketime=taketime,tags=tags,sitename=sitename)


@app.route('/main-search-kw-<query>-requests-<int:page>.html',methods=['GET','POST'])
#@cache.cached(timeout=60*60,key_prefix=make_cache_key)
def search_results_byrequests(query,page=1):
    sensitivewordslist=sensitivewords()
    for word in sensitivewordslist:
        if word.search(query):
            return redirect(url_for('index'))
    connzsky = MySQLdb.connect(host=DB_HOST,port=DB_PORT_MYSQL,user=DB_USER,password=DB_PASS,db=DB_NAME_MYSQL,charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
    currzsky = connzsky.cursor()
    taginsertsql = 'REPLACE INTO search_tags(tag) VALUES(%s)'
    currzsky.execute(taginsertsql,[query])
    connzsky.commit()
    currzsky.close()
    connzsky.close()
    conn,curr = sphinx_conn()
    querysql='SELECT * FROM film WHERE MATCH(%s) ORDER BY requests DESC limit %s,20 OPTION max_matches=50000'
    curr.execute(querysql,[query,(page-1)*20])
    result=curr.fetchall()
    #countsql='SELECT COUNT(*)  FROM film WHERE MATCH(%s)'
    countsql='SHOW META'
    curr.execute(countsql)
    resultcounts=curr.fetchall()
    counts=int(resultcounts[0]['Value'])
    taketime=float(resultcounts[2]['Value'])
    sphinx_close(curr,conn)
    pages=(counts+19)/20
    tags=Search_Tags.query.order_by(Search_Tags.id.desc()).limit(50)
    form=SearchForm()
    form.search.data=query
    return render_template('list_byrequests.html',form=form,query=query,pages=pages,page=page,hashs=result,counts=counts,taketime=taketime,tags=tags,sitename=sitename)

@app.route('/hash/<info_hash>.html',methods=['GET','POST'])
#@cache.cached(timeout=60*60,key_prefix=make_cache_key)
def detail(info_hash):
    conn,curr = sphinx_conn()
    querysql='SELECT * FROM film WHERE info_hash=%s'
    curr.execute(querysql,[info_hash])
    result=curr.fetchone()
    sphinx_close(curr,conn)
    #hash=Search_Hash.query.filter_by(id=id).first()
    if not result:
        return redirect(url_for('index'))        
    fenci_list=jieba.analyse.extract_tags(result['name'], 4)
    tags=Search_Tags.query.order_by(Search_Tags.id.desc()).limit(20)
    form=SearchForm()
    return render_template('detail.html',form=form,tags=tags,hash=result,fenci_list=fenci_list,sitename=sitename)


@app.route('/sitemap.xml')
def sitemap():    
    conn,curr = sphinx_conn()
    querysql='SELECT info_hash,create_time FROM film order by create_time desc limit 100'
    curr.execute(querysql)
    rows=curr.fetchall()
    sphinx_close(curr,conn)
    sitemaplist=[]
    for row in rows:
        info_hash = row['info_hash']
        mtime = datetime.datetime.fromtimestamp(int(row['create_time'])).strftime('%Y-%m-%d')
        url = domain+'hash/{}.html'.format(info_hash)
        url_xml = '<url><loc>{}</loc><lastmod>{}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>'.format(url, mtime)
        sitemaplist.append(url_xml)
    xml_content = '<?xml version="1.0" encoding="UTF-8"?><urlset>{}</urlset>'.format("".join(x for x in sitemaplist))
    with open('static/sitemap.xml', 'wb') as f:
        f.write(xml_content)
        f.close()
    return send_from_directory(app.static_folder, request.path[1:])

@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])

@app.route('/uploads/<filename>')
def uploadpics(filename):
    return send_from_directory(file_path, filename)

@app.errorhandler(404)
def notfound(e):
    return render_template("404.html"),404


class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login_view'))
        connzsky = MySQLdb.connect(host=DB_HOST,port=DB_PORT_MYSQL,user=DB_USER,password=DB_PASS,db=DB_NAME_MYSQL,charset=DB_CHARSET, cursorclass=MySQLdb.cursors.DictCursor)
        currzsky = connzsky.cursor()
        totalsql = 'select max(id) from search_hash'
        currzsky.execute(totalsql)
        totalcounts=currzsky.fetchall()
        total=int(totalcounts[0]['max(id)'])
        todaysql='select count(id) from search_hash where to_days(search_hash.create_time)= to_days(now())'
        currzsky.execute(todaysql)
        todaycounts=currzsky.fetchall()
        today=int(todaycounts[0]['count(id)'])
        currzsky.close()
        connzsky.close()
        return self.render('admin/index.html',total=total,today=today)
    @expose('/login/', methods=('GET', 'POST'))
    def login_view(self):
        form = LoginForm(request.form)
        if helpers.validate_form_on_submit(form):
            user = form.get_user()
            if user is None:
                flash('用户名不存在！')
            elif not check_password_hash(user.password, form.password.data):
                flash('密码错误！')
            elif user is not None and check_password_hash(user.password, form.password.data):
                login_user(user)
        if current_user.is_authenticated:
            return redirect(url_for('admin.index'))
        self._template_args['form'] = form
        #self._template_args['link'] = link
        return super(MyAdminIndexView, self).index()
    @expose('/logout/')
    def logout_view(self):
        logout_user()
        return redirect(url_for('admin.index'))

    
class HashView(ModelView):
    create_modal = True
    edit_modal = True
    can_export = True
    column_default_sort = ('id', True)
    column_searchable_list = ['name','info_hash']
    def get_list(self, *args, **kwargs):
        count, data = super(HashView, self).get_list(*args, **kwargs)
        count=10000
        return count,data
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


class TagsView(ModelView):
    column_default_sort = ('id', True)
    column_searchable_list = ['tag']
    create_modal = True
    edit_modal = True
    can_export = True
    column_searchable_list = ['tag']
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


class KeywordsView(ModelView):
    column_labels = {
        'keyword': u'推荐关键字',
        'order' : u'顺序',
        'pic':u'图片URL',
        'score':u'评分',
    }
    column_default_sort = ('id', True)
    column_searchable_list = ['keyword']
    create_modal = True
    edit_modal = True
    can_export = True
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))

class UserView(ModelView):
    #column_exclude_list = 'password'
    create_modal = True
    edit_modal = True
    can_export = True
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))

class StatusreportView(ModelView):
    column_default_sort = ('date', True)
    create_modal = True
    edit_modal = True
    can_export = True
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))

class FileManager(FileAdmin):
    def is_accessible(self):
        if current_user.is_authenticated :
            return True
        return False
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


admin = Admin(app,name='管理中心',base_template='admin/my_master.html',index_view=MyAdminIndexView(name='首页',template='admin/index.html',url='/admin'))
admin.add_view(HashView(Search_Hash, db.session,name='磁力Hash'))
admin.add_view(KeywordsView(Search_Keywords, db.session,name='首页推荐'))
admin.add_view(TagsView(Search_Tags, db.session,name='搜索记录'))
admin.add_view(StatusreportView(Search_Statusreport, db.session,name='爬取统计'))
admin.add_view(FileManager(file_path, '/uploads/', name='文件管理'))
admin.add_view(UserView(User, db.session,name='用户管理'))


@manager.command
def init_db():
    db.create_all()
    db.session.commit()


@manager.option('-u', '--name', dest='name')
@manager.option('-e', '--email', dest='email')
@manager.option('-p', '--password', dest='password')
def create_user(name,password,email):
    if name is None:
        name = raw_input('输入用户名(默认admin):') or 'admin'
    if password is None:
        password = generate_password_hash(getpass('密码:'))
    if email is None:
        email=raw_input('Email地址:')
    user = User(name=name,password=password,email=email)
    db.session.add(user)
    db.session.commit()
    print("管理员创建成功!")

@manager.option('-np', '--newpassword', dest='newpassword')
def changepassword(newpassword):
    name = raw_input(u'输入用户名:')
    thisuser = User.query.filter_by(name=name).first()
    if not thisuser:
        print("用户不存在,请重新输入用户名!")
        name = raw_input(u'输入用户名:')    
        thisuser = User.query.filter_by(name=name).first()
    if newpassword is None:
        newpassword = generate_password_hash(getpass(u'新密码:'))
    thisuser.password=newpassword
    db.session.add(thisuser)
    db.session.commit()
    print("密码已更新,请牢记新密码!")

if __name__ == '__main__':
    manager.run()
