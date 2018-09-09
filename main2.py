import webapp2

def func_run_in_bg(val):
  import logging
  logging.debug(u'val = {}'.format(val))


def another_func_run_in_bg(val):
  import logging
  logging.debug(u'val = {}'.format(val))


from google.appengine.ext.deferred.deferred import TaskHandler
from google.appengine.ext.deferred.deferred import PermanentTaskFailure
from google.appengine.ext.deferred.deferred import _DEFAULT_LOG_LEVEL

class MyTaskHandler(TaskHandler):
  def dispatch(self):
    import logging
    logging.debug('using the handler: {}'.format(self.__class__.__name__))
    if self.is_xsrf():
      self.response.set_status(403)
      return

    super(MyTaskHandler, self).dispatch()

  def is_xsrf(self):
    '''Just copy from TaskHandler.run_from_request.'''
    import logging
    if "X-AppEngine-TaskName" not in self.request.headers:
      logging.error("Detected an attempted XSRF attack. The header "
                    '"X-AppEngine-Taskname" was not set.')
      return True

    in_prod = (
        not self.request.environ.get("SERVER_SOFTWARE").startswith("Devel"))
    if in_prod and self.request.environ.get("REMOTE_ADDR") != "0.1.0.2":
      logging.error("Detected an attempted XSRF attack. This request did "
                    "not originate from Task Queue.")
      return True
    return False


  def print_headers(self):
    '''The original section for printing the headers print only the
    X-Appengine-* like headers. You probably want the Referer too as it
    indicates the caller script! You can find the same info the protopayload
    too.
    '''
    import logging
    headers = ["%s:%s" % (k, v) for k, v in self.request.headers.iteritems()]
    logging.log(_DEFAULT_LOG_LEVEL, "\n".join(headers))


  def run(self):
    """Unpickles and executes a task.

    Args:
      data: A pickled tuple of (function, args, kwargs) to execute.
    Returns:
      The return value of the function invocation.
    """
    # this is a modified version google.appengine.ext.deferred.deferred.run
    try:
      import pickle
      func, args, kwds = pickle.loads(self.request.body)
    except Exception as e:
      # Failed to unpickle
      raise PermanentTaskFailure(e)
    else:
      # unpickled
      import logging
      logging.log(_DEFAULT_LOG_LEVEL, 'execute function {}'.format(func.__name__))
      return func(*args, **kwds)

  def run_from_request(self):
    self.print_headers()
    self.run()



class MainPage(webapp2.RequestHandler):
  def get(self):
    from google.appengine.ext import deferred
    deferred.defer(func_run_in_bg, val=10, _url='/2/deferred/my_deferred1')
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.write('Hello, Deferred. I created two deferred tasks.')
    deferred.defer(another_func_run_in_bg, val=20, _url='/2/deferred/my_deferred2')
    # Too lazy to name a path (o:
    deferred.defer(another_func_run_in_bg, val=15, _url='/2/deferred/')


app = webapp2.WSGIApplication([
  ('/2/', MainPage),
  ('/2/deferred/.*', MyTaskHandler),
  ], debug=True)
