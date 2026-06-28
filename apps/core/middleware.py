from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ActiveSubscriptionMiddleware:
    """
    If a provider (landlord/sme/auto) tries to access listing creation
    without an active subscription, redirect them to the plan chooser.
    All other routes pass through untouched.
    """
    GATED_PATHS = ['/listings/create/', '/listings/edit/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.PAYMENTS_ENABLED
            and
            request.user.is_authenticated
            and request.user.is_provider
            and any(request.path.startswith(p) for p in self.GATED_PATHS)
            and not request.user.active_subscription
        ):
            return redirect(reverse('subscriptions:choose_plan'))

        return self.get_response(request)
