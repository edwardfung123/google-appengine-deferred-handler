# Google AppEngine deferred library with customized request handler

## Prerequisite

If you didn't know what deferred library is, you should check out [this nice article](https://cloud.google.com/appengine/articles/deferred) by Google. By the way, it is a feature supported by the 1st generation runtime only. Hopefully, Google or someone will make this handy feature available in the 2nd generation runtimes as well.

## Introduction

It is sometimes desired to have customized request handler when using the `deferred` library. For example, in a complex enough production application, debugging `deferred` requests is a PITA. It is because all the requests are handled by one single request handler. It is impossible to filter the server log without manually logging the function name such as `logging.debug('in some_deferred_func')` in the very beginning of the target function.

Here is some simplified version. Just to illustrate the idea.

`main.py`:

```python
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
```

`app.yaml`:

```yaml
runtime: python27
api_version: 1
threadsafe: true

builtins:
- deferred: on

handlers:
- url: /_ah/queue/deferred
  script: google.appengine.ext.deferred.deferred.application
  login: admin
- url: /.*
  script: main.app
```

## Dive deep into the library

To fully understand the `deferred` library, we have to deep dive into the source code. In fact, many of the Google AppEngine source code is "partially" publicly visible. It doesn't mean it is "open-source". You can view the [source code online](https://cloud.google.com/appengine/docs/standard/python/refdocs/modules/google/appengine/ext/deferred/deferred) or open it locally if you have the Google Cloud SDK + appengine python component installed. The code is located in `$gcloud_sdk/platform/google_appengine/google/appengine/ext/deferred/` and the most of its logic is inside `deferred.py`.

By the way, Google also puts the source code for `ndb` and `images` services in similar fashion. Of course, Google does not reveal the implementation of the underlying services. Almost all the services you used in GAE will eventually send the requests to the blackbox using RPC. What you are reading are most likely some wrappers or _high level_ library calls.

A few interesting things:

1. When you call `eferred.defer()`, some of the named arguments prefixed with `_` will be extracted and passed to the underlying `taskqueue.Task()` and `Task.add()` call.
2. If you are curious how the function and its arguments are passed to the `taskqueue`, you may take a look at the function `_curry_callable`. It is also why we have some weird import issue with the `deferred` library.
3. The `deferred` library basically `pickle` the function and its arguments, put them into the `taskqueue` with a PUSH queue. The request handler `unpickle` the request body and get back the function and the arguments.

A note about the request handler, as of the library was written, `webapp2` was probably not available to GAE. When `webapp2` is introduced in GAE, it is backward compatible and all `webapp` references are aliased to `webapp2`. That's why some old libraries still work and the applications do not need to be updated. See [reference](https://cloud.google.com/appengine/docs/standard/python/migrate27#webapp2).

## Creating our own task handler (v1)

To use our own request handler, we need to:

1. Extend the TaskHandler and create our own request handler class
2. Specify the `_url` when calling `deferred.defer()`

Here is the example:

`main2.py`:

```python
import webapp2

def func_run_in_bg(val):
  import logging
  logging.debug('Running in func_run_in_bg')
  logging.debug(u'val = {}'.format(val))

def another_func_run_in_bg(val):
  import logging
  logging.debug('Running in another_func_run_in_bg')
  logging.debug(u'val = {}'.format(val))


from google.appengine.ext.deferred.deferred import TaskHandler

class MyTaskHandler(TaskHandler):
  def dispatch(self):
    import logging
    logging.debug('using the handler: {}'.format(self.__class__.__name__))
    super(MyTaskHandler, self).dispatch()


class MainPage(webapp2.RequestHandler):
  def get(self):
    from google.appengine.ext import deferred
    deferred.defer(func_run_in_bg, val=10, _url='/2/my_deferred1')
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.write('Hello, Deferred. I created two deferred tasks.')
    deferred.defer(another_func_run_in_bg, val=10, _url='/2/my_deferred2')


app = webapp2.WSGIApplication([
  ('/2/', MainPage),
  ('/2/my_deferred1', MyTaskHandler),
  ('/2/my_deferred2', MyTaskHandler),
  ], debug=True)
```

However, we still need to print the deferred function name explicitly in the function itself. To automate it, we need to take a few more steps.

## Creating our own task handler (v2)

The default deferred TaskHandler is not that extensible. It turns out that I need to copy and paste the source code and reinvent the wheel a bit. Hopefully, I just need to do this once...

```python
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
```

In this case, we mount a general "deferred request handler" in the path `/2/deferred/.*` so that we can lazily call `deferred.defer(another_func_run_in_bg, val=15, _url='/2/deferred/')` instead of `/2/deferred/sth_here`.

## Conclusion

By studying the source code of the `deferred` library at `$gcloud_sdk/platform/google_appengine/google/appengine/ext/deferred/deferred.py`, we successfully create our own version of deferred task request handler. Our version will print the name of deferred function implicitly before executing the function. The developer can also mount the request handler to any endpoint (E.g. `/system/deferred/some/path`). With these two features, the developer can isolate the logs easily which is crucial for debugging.