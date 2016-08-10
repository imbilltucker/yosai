class WebRegistrySettings:

    def __init__(self, settings):
        wr_config = settings.WEB_REGISTRY
        self.signed_cookie_secret = wr_config.get('signed_cookie_secret')
