from django.core.checks import Error, register

from apps.pages.services import iter_blog_post_validation_errors


@register()
def blog_post_content_check(app_configs, **kwargs):
    return [
        Error(
            str(error),
            hint="Fix the Markdown frontmatter in apps/pages/posts before deploying.",
            id="blog.E001",
        )
        for error in iter_blog_post_validation_errors()
    ]
