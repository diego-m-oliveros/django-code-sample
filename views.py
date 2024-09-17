import datetime
import dateutil.parser as dparser
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.views import View

from atlasmind.account.models import Account, AccountUser
from atlasmind.dashboard.models import Dashboard, AccountDashboard, Report, ReportType
from atlasmind.dashboard.util import set_session_start_date_end_date, get_session_start_date_end_date, \
    render_daily_email_from_dashboard, get_ordered_reports_for_dashboard_for_date
from atlasmind.dashboard import report_renderers


@login_required
def index(request):
    account = request.user.account
    account_user = request.user.account_user
    try:
        if account_user.default_dashboard:
            default_dashboard = account_user.default_dashboard
        else:
            default_dashboard = AccountDashboard.objects.filter(section__account=account)\
                .filter(Q(account_user=account_user) | Q(account_user__isnull=True))\
                .order_by('order_override', 'dashboard__order')[0]
        return redirect(default_dashboard.get_absolute_url())
    except IndexError:
        return render(request, 'dashboard/dashboard.html', {})


class DashboardDetailView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        account = request.user.account
        account_dashboard = get_object_or_404(AccountDashboard, section__account=account, id=kwargs['dashboard_id'])
        account_user = request.user.account_user
        if account_user and account_user.only_show_user_dashboards and account_dashboard.account_user != account_user:
            raise Http404
        context = {'dashboard': account_dashboard}

        if account_dashboard:
            date = get_session_start_date_end_date(request)[1]
            ordered_reports = get_ordered_reports_for_dashboard_for_date(account_dashboard, date)
            context.update({'reports': ordered_reports,
                            'current_dashboard': account_dashboard})
        return render(request, 'dashboard/dashboard.html', context)


class ReportContentsView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if request.user.username == 'emailuser':
            account = Account.objects.get(id=request.GET.get('a', ''))
        else:
            account = request.user.account
        report = get_object_or_404(Report, account=account, id=kwargs['report_id'])
        rendered_report = report_renderers.render_report(report, request)
        return HttpResponse(rendered_report)


class DashboardSettingsView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        referrer = request.META['HTTP_REFERER']
        url_path = urlparse(referrer).path
        start_date = request.POST.get('start_date', None)
        if start_date:
            start_date = dparser.parse(start_date, fuzzy=True)
        end_date = request.POST.get('end_date', None)
        if end_date:
            end_date = dparser.parse(end_date, fuzzy=True)
        set_session_start_date_end_date(request, start_date, end_date)

        aggregate = request.POST.get('aggregate', None)
        current_aggregate = request.session.get('aggregate_tables', False)
        if aggregate:
            request.session['aggregate_tables'] = (not current_aggregate)

        text_filter = request.POST.get('text_filter', None)
        remove_filter = request.POST.get('remove_filter', None)
        text_filters = request.session.get('text_filters', {})
        if text_filter:
            text_filters[url_path] = text_filter
        if remove_filter:
            text_filters[url_path] = None
        request.session['text_filters'] = text_filters
        return redirect(referrer)


class ExportCSVView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        report_id = request.POST.get('report_id', None)
        if report_id:
            report = get_object_or_404(Report, id=report_id)
            temp_csv_file = report_renderers.render_csv(report, request)

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="export.csv"'
            temp_file = open(temp_csv_file.name, 'r')
            response.write(temp_file.read())
            return response
        else:
            raise Http404


class DailyEmailView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            if request.user.username != 'emailuser':
                raise Http404
        account = Account.objects.get(id=kwargs['account_id'])
        account_user = AccountUser.objects.get(id=request.GET.get('user_id', None))
        date_override = request.GET.get('date', None)
        user_dashboard = account_user.default_dashboard
        default_dashboard = AccountDashboard.objects.filter(section__account=account).order_by('order_override', 'dashboard__order').first()
        if not user_dashboard:
            dashboard_to_use = default_dashboard
        else:
            dashboard_to_use = default_dashboard #TODO: use the user's dashboard preference user_dashboard

        if dashboard_to_use:
            if not date_override:
                date = get_session_start_date_end_date(request)[1]
            else:
                date = dparser.parse(date_override, fuzzy=True)

            rendered_email = render_daily_email_from_dashboard(account, dashboard_to_use, date)
            return HttpResponse(rendered_email)

        else:
            raise Http404
