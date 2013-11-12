from gluon.storage import Storage
settings = Storage()

settings.migrate = True
settings.title = 'FFlock Distributed Cluster Transcoding'
settings.subtitle = ''
settings.author = 'Eric Griffin'
settings.author_email = 'webmaster@fflock.com'
settings.keywords = 'fflock, transcoding, cluster'
settings.description = ''
settings.layout_theme = 'Default'
settings.database_uri = 'sqlite://storage.sqlite'
settings.security_key = '89465294-76ab-4323-90d7-f157bd412ffc'
settings.email_server = 'localhost'
settings.email_sender = 'webmaster@fflock.com'
settings.email_login = ''
settings.login_method = 'local'
settings.login_config = ''
settings.plugins = []
