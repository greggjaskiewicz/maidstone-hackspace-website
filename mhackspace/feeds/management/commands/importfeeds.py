from django.core.management.base import BaseCommand
from mhackspace.feeds.helper import import_feeds


class Command(BaseCommand):
    help = 'Imports the RSS feeds from active blogs'

    def add_arguments(self, parser):
        parser.add_argument(
            'blog_id',
            nargs='*',
            type=int,
            default=False,
            help='Specify a blog to get feeds form'
        )

    def handle(self, *args, **options):
        imported = import_feeds(options['blog_id'])
        self.stdout.write(
            self.style.SUCCESS(
                'Successfully imported %s articles' % len(imported)))
