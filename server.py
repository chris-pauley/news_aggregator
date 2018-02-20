from flask import Flask, request, redirect, url_for, session, Response
import sys, json, base64, time
import mysql.connector
from functools import wraps
import numpy
import tldextract

app = Flask(__name__)

config = {}
with open('config.json','r') as config_file:
	config = json.loads(config_file.read())

c = None
cnx = None
last_db_conn = 0

def reconnect():
	global cnx, c, last_db_conn
	cnx = mysql.connector.connect(host=config['database']['host'], user=config['database']['user'], db=config['database']['database'])
	c = cnx.cursor()
	last_db_conn = time.time()

reconnect()

# Easy function to maintain connection to db
def db_route(func):
	@wraps(func)
	def func_wrapper():
		global c, cnx, last_db_conn
		now = time.time()
		if now - last_db_conn > 3600:
			reconnect()
	return func

# All routes prefixed /api

def get_param(name):
	res = request.args.get(name, None)
	if res is None:
		res = request.form.get(name, None)
	return res

@app.route('/api/rate', methods=['POST'])
@db_route
def rate_route():
	global c, cnx
	link_id = get_param('post_id',None)
	score_modifier = get_param('score', None)

	c.execute("INSERT INTO posts_scores (post_id, score) VALUES (%s, %s)", [link_id, score_modifier])
	cnx.commit()

@app.route('/api/list', methods=['GET'])
@db_route
def list_route():
	global c, cnx
	c.execute("SELECT posts.id, posts.title, posts.body, posts.url, UNIX_TIMESTAMP(posts.date_created), sources.id, sources.link FROM posts LEFT JOIN sources ON posts.source_id=sources.id")
	posts = []
	posts_sources = {}
	sites = defaultdict(lambda: [])
	source_scores = defaultdict(lambda: [])
	source_score_avg = 0.0
	for row in c.fetchall():
		posts.append({
			'id': row[0],
			'title': unicode(row[1]),
			'body': unicode(row[2]),
			'url': unicode(row[3]),
			'date_created': row[4],
			'source_id': row[5],
			'via': row[6]
			})
		posts_sources[row[1]] = row[5]
		site_domain = tldextract.extract(row[2])
		if site_domain == '.' or site_domain == 'www':
			site_domain = '.'.join([site_domain['domain'], site_domain['suffix']])
		else:
			site_domain = '.'.join([site_domain['subdomain'], site_domain['domain'], site_domain['suffix']])
		
	c.execute("SELECT posts.source_id, score FROM post_scores LEFT JOIN posts ON post_id=posts.id")
	for row in c.fetchall():
		source_scores[row[0]].append(row[1])

	#get an average for building
	source_score_totals = []
	for source, scores in source_scores.iteritems():
		source_score_totals.append(float(sum(scores)))

	source_score_avg = numpy.mean(source_score_totals)
	source_score_std = numpy.std(source_score_totals)


	now = time.time()
	def ts_to_score(ts):
		days = int((now - ts) / 86400.0)
		return float(0 - days)

	def source_to_score(source_id):
		source_score = sum(source_scores[source_id])
		if source_score == 0:
			return 0
		return float(source_score - source_score_avg) / source_score_std

	for post in posts:
		post['score'] = source_to_score(post['source_id']) + ts_to_score(post['date_created'])


	return Response(response=json.dumps(sorted(posts, key='score', reverse=True), ensure_ascii=False), status=200, mimetype='application/json')

if __name__ == "__main__":
	app.run(port=config['port'])

