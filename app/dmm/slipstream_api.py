import slipstream.api


class Api(slipstream.api.Api):

    def get_deployment_events(self, duid, types=[]):
        filter = "content/resource/href='run/%s'" % duid
        if types:
            filter += " and (%s)" % ' or '.join(map(lambda x: "type='%s'" % x, types))
        return self.cimi_search(resource_type='events', filter=filter)
