from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, Plan, PaymentLog


@login_required
def choose_plan(request):
    if not request.user.is_provider:
        return redirect('core:home')

    if request.method == 'POST':
        plan = request.POST.get('plan', Plan.STANDARD)
        if plan not in [Plan.BASIC, Plan.STANDARD, Plan.PREMIUM]:
            plan = Plan.STANDARD

        # Deactivate any existing subscription
        request.user.subscriptions.filter(is_active=True).update(is_active=False)

        # Create new subscription (pending payment)
        sub = Subscription.objects.create(
            user=request.user,
            plan=plan,
            is_active=False,  # activated after payment confirmed
        )
        request.session['pending_subscription_id'] = str(sub.id)
        return redirect('subscriptions:payment', plan=plan)

    current = request.user.active_subscription
    return render(request, 'subscriptions/choose_plan.html', {
        'current_plan': current,
    })


@login_required
def payment(request, plan):
    """
    Payment page — shows M-Pesa and card options.
    In production: integrate Selcom / Azampay for M-Pesa.
    For now shows the UI + a manual confirmation flow for testing.
    """
    from django.conf import settings
    plan_info = settings.PLAN_LIMITS.get(plan, {})

    if request.method == 'POST':
        # Simulate payment confirmation (replace with real gateway callback)
        sub_id = request.session.get('pending_subscription_id')
        if sub_id:
            try:
                sub = Subscription.objects.get(id=sub_id, user=request.user)
                sub.is_active = True
                sub.expires_at = timezone.now() + timedelta(days=30)
                sub.amount_paid_tzs = plan_info.get('price_tzs', 0)
                sub.payment_reference = request.POST.get('reference', 'manual')
                sub.save()

                PaymentLog.objects.create(
                    subscription=sub,
                    user=request.user,
                    amount_tzs=plan_info.get('price_tzs', 0),
                    method=request.POST.get('method', 'mpesa'),
                    reference=request.POST.get('reference', ''),
                    status='confirmed',
                )

                request.session.pop('pending_subscription_id', None)
                messages.success(request, f'Payment confirmed. Your {sub.get_plan_display()} plan is now active!')
                return redirect('listings:create')
            except Subscription.DoesNotExist:
                messages.error(request, 'Subscription not found.')

    return render(request, 'subscriptions/payment.html', {
        'plan': plan,
        'plan_info': plan_info,
    })


@login_required
def manage(request):
    sub = request.user.active_subscription
    history = request.user.payment_logs.all()[:10]
    return render(request, 'subscriptions/manage.html', {
        'subscription': sub,
        'payment_history': history,
    })
