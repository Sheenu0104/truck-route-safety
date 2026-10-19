from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from django.urls import include, path, re_path


def spa_index(request: HttpRequest) -> HttpResponse:
    """Serve the React app for any non-API path (client-side routing fallback)."""
    index = settings.FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index.open("rb"), content_type="text/html")
    return HttpResponse(
        "Front end not built. Run `npm run dev` in /frontend (it proxies /api here), "
        "or `npm run build` to serve it from Django.",
        content_type="text/plain",
    )


urlpatterns = [
    path("api/", include("routeplanner.urls")),
    re_path(r"^(?!api/).*$", spa_index),
]
