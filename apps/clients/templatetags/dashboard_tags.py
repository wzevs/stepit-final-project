from django import template

register = template.Library()


@register.filter
def ka(status, labels):
    return labels.get(status, status)
