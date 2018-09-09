import webapp2

def func_run_in_bg(val):
  import logging
  logging.debug('Running in func_run_in_bg')
  logging.debug(u'val = {}'.format(val))


def another_func_run_in_bg(val):
  import logging
  logging.debug('Running in another_func_run_in_bg')
  logging.debug(u'val = {}'.format(val))



class MainPage(webapp2.RequestHandler):
  def get(self):
    from google.appengine.ext import deferred
    deferred.defer(func_run_in_bg, val=10)
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.write('Hello, Deferred. I created two deferred tasks.')
    deferred.defer(another_func_run_in_bg, val=10)


app = webapp2.WSGIApplication([
  ('/', MainPage),
  ], debug=True)
