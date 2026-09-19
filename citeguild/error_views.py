"""Error responses must not depend on authentication or database connections."""

from django.http import HttpResponseNotFound
from django.template.loader import get_template
from django.views.decorators.csrf import requires_csrf_token


@requires_csrf_token
def page_not_found(request, exception):
    # In particular, an ASGI exception handler may run in a different thread
    # from the view. Do not run profile/context-processor queries to render 404s.
    return HttpResponseNotFound(get_template("404.html").render({}))
