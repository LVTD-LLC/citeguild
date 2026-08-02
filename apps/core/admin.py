from django.contrib import admin

from apps.core.models import (
    Article,
    ArticleCrawlAttempt,
    ArticleSourceURL,
    EmailSent,
    OutboundLinkObservation,
    PageCrawlWork,
    PageExtractionResult,
    Project,
    ProjectStateTransition,
    ProjectSyncRequest,
    SitemapCandidate,
    SitemapInventory,
)

admin.site.register(EmailSent)
admin.site.register(Project)
admin.site.register(ProjectStateTransition)
admin.site.register(ProjectSyncRequest)
admin.site.register(SitemapInventory)
admin.site.register(SitemapCandidate)
admin.site.register(PageCrawlWork)
admin.site.register(PageExtractionResult)
admin.site.register(Article)
admin.site.register(ArticleSourceURL)
admin.site.register(ArticleCrawlAttempt)
admin.site.register(OutboundLinkObservation)
