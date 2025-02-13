import datetime
import json
import logging
import pprint
from urllib import parse
from urllib.parse import quote

import django
import trio
from django.conf import settings as project_settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import text

from bdr_deposits_uploader_app.forms.staff_form import StaffForm
from bdr_deposits_uploader_app.forms.student_upload_form import make_student_upload_form_class
from bdr_deposits_uploader_app.lib import config_new_helper, version_helper
from bdr_deposits_uploader_app.lib.shib_handler import shib_decorator
from bdr_deposits_uploader_app.lib.version_helper import GatherCommitAndBranchData
from bdr_deposits_uploader_app.models import AppConfig

log = logging.getLogger(__name__)


# -------------------------------------------------------------------
# main urls
# -------------------------------------------------------------------


def info(request) -> HttpResponse:
    """
    The "about" view.
    Can get here from 'info' url, and the root-url redirects here.
    """
    log.debug('\n\nstarting info()')
    log.debug(f'user, ``{request.user}``')

    ## clear django-session -----------------------------------------
    auth.logout(request)  # TODO: consider forcing shib logout here

    ## prep response ------------------------------------------------
    context = {}
    if request.GET.get('format', '') == 'json':  # TODO: remove this
        log.debug('building json response')
        resp = HttpResponse(
            json.dumps(context, sort_keys=True, indent=2),
            content_type='application/json; charset=utf-8',
        )
    else:
        log.debug('building template response')
        resp = render(request, 'info.html', context)
    return resp


def pre_login(request) -> HttpResponseRedirect:
    """
    Ensures shib actually comes up for user.

    Triggered by clicking "Staff Login" on the public info page.

    Flow:
    - Checks "logout_status" session-key for 'forcing_logout'.
        - If not found (meaning user has come, from, say, the public info page by clicking "Staff Login")...
            - Builds the IDP-shib-logout-url with `return` param set back to here.
            - Sets the "logout_status" session key-val to 'forcing_logout'.
            - Redirects to the IDP-shib-logout-url.
        - If found (meaning we're back here after redirecting to the shib-logout-url)...
            - Clears the "logout_status" session key-val.
            - Builds the IDP-shib-login-url with `next` param set to the `config-new` view.
            - Redirects to the IDP-shib-login-url.
    """
    log.debug('\n\nstarting pre_login()')
    ## get the type-value -------------------------------------------
    type_value = request.GET.get('type', None)
    log.debug(f'type_value from GET, ``{type_value}``')
    if type_value not in ['staff', 'student']:  ## try to get the type from the session
        log.debug('type_value not in [staff, student]')
        type_value = request.session.get('type', None)
        log.debug(f'type_value from session, ``{type_value}``')
    if type_value not in ['staff', 'student']:  ## if still not found, default to 'staff'
        log.warning('type_value not in [staff, student]')
        type_value = 'student'
    request.session['type'] = type_value
    ## check for session "logout_status" ----------------------------
    logout_status = request.session.get('logout_status', None)
    log.debug(f'logout_status, ``{logout_status}``')
    if logout_status != 'forcing_logout':
        ## meaning user has come directly, from, say, the public info page by clicking "Staff Login"
        ## set logout_status ----------------------------------------
        request.session['logout_status'] = 'forcing_logout'
        log.debug(f'logout_status set to ``{request.session["logout_status"]}``')
        ## build IDP-shib-logout-url --------------------------------
        # full_pre_login_url = f'{request.scheme}://{request.get_host()}{reverse("pre_login_url")}'
        full_pre_login_url = f'{request.scheme}://{request.get_host()}{reverse("pre_login_url")}?type={type_value}'
        log.debug(f'full_pre_login_url, ``{full_pre_login_url}``')
        encoded_full_pre_login_url = parse.quote(full_pre_login_url, safe='')
        redirect_url = f'{project_settings.SHIB_IDP_LOGOUT_URL}?return={encoded_full_pre_login_url}'
    else:  # request.session['logout_status'] _is_ found -- meaning user is back after hitting the IDP-shib-logout-url
        ## clear logout_status --------------------------------------
        del request.session['logout_status']
        log.debug('logout_status cleared')
        ## build IDP-shib-login-url ---------------------------------
        if type_value == 'staff':
            full_authenticated_new_url = f'{request.scheme}://{request.get_host()}{reverse("config_new_url")}'
        elif type_value == 'student':
            full_authenticated_new_url = f'{request.scheme}://{request.get_host()}{reverse("upload_url")}'
        log.debug(f'full_config_new_url, ``{full_authenticated_new_url}``')
        if request.get_host() == '127.0.0.1:8000':  # eases local development
            redirect_url = full_authenticated_new_url
        else:
            encoded_full_config_new_url = parse.quote(full_authenticated_new_url, safe='')
            redirect_url = f'{project_settings.SHIB_SP_LOGIN_URL}?target={encoded_full_config_new_url}'
    log.debug(f'redirect_url, ``{redirect_url}``')
    return HttpResponseRedirect(redirect_url)

    ## end def pre_login()


@shib_decorator
def shib_login(request) -> HttpResponseRedirect:
    """
    Handles authentication and initial authorization via shib.

    Then:
    - On successful further UserProfile authorization, logs user in and redirects to the `next_url`.
        - If no `next_url`, redirects to the `info` page.

    Called automatically by attempting to access an `@login_required` view.
    """
    log.debug('\n\nstarting login()')
    next_url: str | None = request.GET.get('next', None)
    log.debug(f'next_url, ```{next_url}```')
    if not next_url:
        redirect_url = reverse('info_url')
    else:
        redirect_url = request.GET['next']  # may be same page
    log.debug('redirect_url, ```%s```' % redirect_url)
    return HttpResponseRedirect(redirect_url)


def logout(request) -> HttpResponseRedirect:
    """
    Flow:
    - Clears django-session.
    - Hits IDP shib-logout url.
    - Redirects user to info page.
    """
    log.debug('\n\nstarting logout()')
    ## clear django-session -----------------------------------------
    auth.logout(request)
    ## build redirect-url -------------------------------------------
    redirect_url: str = f'{request.scheme}://{request.get_host()}{reverse("info_url")}'
    if request.get_host() == '127.0.0.1' and project_settings.DEBUG == True:  # eases local development  # noqa: E712
        pass  # will redirect right to the info url
    else:
        ## build shib-logout-url -------------------------------------
        encoded_return_param_url: str = quote(redirect_url, safe='')
        redirect_url: str = f'{project_settings.SHIB_IDP_LOGOUT_URL}?return={encoded_return_param_url}'
    log.debug(f'redirect_url, ``{redirect_url}``')
    return HttpResponseRedirect(redirect_url)


@login_required
def config_new(request) -> HttpResponse:
    """
    Enables initial specification of new app name and slug.
    """
    log.debug('\n\nstarting config_new()')
    log.debug(f'user, ``{request.user}``')
    if not request.user.userprofile.can_create_app:
        log.debug(f'user ``{request.user}`` does not have permissions to create an app')
        return HttpResponse('You do not have permissions to create an app.')
    apps_data: list = config_new_helper.get_configs()
    log.debug(f'apps_data, ``{pprint.pformat(apps_data)}``')
    hlpr_check_name_and_slug_url = reverse('hlpr_check_name_and_slug_url')
    hlpr_generate_slug_url = reverse('hlpr_generate_slug_url')
    context = {
        'hlpr_check_name_and_slug_url': hlpr_check_name_and_slug_url,
        'hlpr_generate_slug_url': hlpr_generate_slug_url,
        'recent_apps': apps_data,
        'username': request.user.first_name,
    }
    return render(request, 'config_new.html', context)


@login_required
def config_slug(request, slug) -> HttpResponse | HttpResponseRedirect:
    log.debug('\n\nstarting config_slug()')
    log.debug(f'slug, ``{slug}``')
    if not request.user.userprofile.can_create_app:
        log.debug('user does not have permissions to create an app')
        resp = HttpResponse('You do not have permissions to configure this app.')
    else:
        log.debug('user has permissions to configure app')
        app_config = get_object_or_404(AppConfig, slug=slug)
        log.debug(f'app_config, ``{app_config}``')
        log.debug(f'app_config, ``{app_config.__dict__}``')
        if request.method == 'POST':
            log.debug(f'POST data, ``{request.POST}``')
            form = StaffForm(request.POST)
            log.debug('about to call is_valid()')
            if form.is_valid():
                ## save all the cleaned form data into the temp_config_json field
                app_config.temp_config_json = form.cleaned_data
                app_config.save()
                log.debug('Saved cleaned_data to app_config.temp_config_json')
                resp = redirect(reverse('config_new_url'))
            else:
                log.debug('form is not valid')
                log.debug(f'form.errors, ``{form.errors}``')
                log.debug(f'form.non_field_errors, ``{form.non_field_errors}``')
                for field in form:
                    if field.errors:
                        log.debug(f'field.errors for {field.name}: {field.errors}')
                        log.debug(f'field label: {field.label}')
                resp = render(
                    request,
                    'staff_form.html',
                    {'form': form, 'slug': slug, 'username': request.user.first_name},
                )
        else:  # GET
            ## load existing data to pre-populate the form.
            initial_data = app_config.temp_config_json or {}
            form = StaffForm(initial=initial_data)
            resp = render(
                request,
                'staff_form.html',
                {'form': form, 'slug': slug, 'app_name': app_config.name, 'username': request.user.first_name},
            )
    return resp


@login_required
def upload(request) -> HttpResponse:
    """
    Default info landing page for student-login.
    """
    log.debug('\n\nstarting upload()')
    log.debug(f'user, ``{request.user}``')
    context = {
        'username': request.user.first_name,
    }
    return render(request, 'uploader_select.html', context)


@login_required
def upload_slug(request, slug) -> HttpResponse | HttpResponseRedirect:
    """
    Displays the student-upload-form.
    """
    log.debug('\n\nstarting upload_slug()')
    log.debug(f'slug, ``{slug}``')

    ## load staff-config data ---------------------------------------
    app_config = get_object_or_404(AppConfig, slug=slug)
    config_data = app_config.temp_config_json

    ## prep other form data -----------------------------------------
    depositor_fullname: str = f'{request.user.first_name} {request.user.last_name}'
    depositor_email: str = request.user.email
    deposit_iso_date: str = datetime.datetime.now().isoformat()

    ## build form based on staff-config data ------------------------
    # StudentUploadForm = get_student_upload_form_class(config_data)
    StudentUploadForm: django.forms.forms.DeclarativeFieldsMetaclass = make_student_upload_form_class(config_data)
    log.debug(f'type(StudentUploadForm), ``{type(StudentUploadForm)}``')

    ## handle POST and GET ------------------------------------------
    if request.method == 'POST':
        form = StudentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # TODO: Process the valid student-upload data, e.g., save to UploadInfo model.
            resp: HttpResponseRedirect = redirect(reverse('upload_successful_url'))
    else:
        form = StudentUploadForm()
        resp: HttpResponse = render(
            request,
            'uploader_slug.html',
            {
                'form': form,
                'slug': slug,
                'username': request.user.first_name,
                'depositor_fullname': depositor_fullname,
                'depositor_email': depositor_email,
                'deposit_iso_date': deposit_iso_date,
                'app_name': app_config.name,
            },
        )
    return resp


def upload_successful(request) -> HttpResponse:
    """
    Displays a success message after a student form is submitted.
    """
    log.debug('\n\nstarting upload_successful()')
    return HttpResponse(
        'Student form submitted successfully; info that staff will be notified to review and ingest the upload will go here.'
    )


# -------------------------------------------------------------------
# htmx helpers
# -------------------------------------------------------------------


def hlpr_generate_slug(request) -> HttpResponse:
    """
    Generates a url slug for given incoming text.
    """
    log.debug('\n\nstarting hlpr_generate_slug()')
    app_name = request.POST.get('new_app_name', '')
    slug = text.slugify(app_name)
    html = f"""<input 
        id="url-slug" 
        name="url_slug" 
        type="text" 
        value="{slug}" 
        placeholder="Auto-generated or enter manually"
         >"""
    log.debug(f'html, ``{html}``')
    return HttpResponse(html)


def hlpr_check_name_and_slug(request) -> HttpResponse | JsonResponse:
    """
    Validates that the incoming app-name and slug are unique.
    """
    log.debug('\n\nstarting hlpr_check_name_and_slug()')

    ## get the incoming data
    app_name: str = request.POST.get('new_app_name', '').strip()
    log.debug(f'app_name, ``{app_name}``')
    slug: str = request.POST.get('url_slug', '').strip()
    log.debug(f'slug, ``{slug}``')

    ## if either are empty, return an error
    if not app_name or not slug:
        # Return an error message for missing inputs
        html = 'Both name and slug are required.'
        log.debug(f'html, ``{html}``')
        return HttpResponse(html)

    ## check for existing names and slugs
    name_already_exists: bool = AppConfig.objects.filter(name__iexact=app_name).exists()
    slug_already_exists: bool = AppConfig.objects.filter(slug__iexact=slug).exists()
    name_problem: str = '' if not name_already_exists else 'Name already exists.'
    slug_problem: str = '' if not slug_already_exists else 'Slug already exists.'

    ## create html to show any problems
    if name_problem or slug_problem:
        html = f'{name_problem} {slug_problem}'
        log.debug(f'html, ``{html}``')
        return HttpResponse(html)

    ## getting here means life is good; use HX-Redirect to handle the redirection
    log.debug('saving data')
    try:
        app_config = AppConfig(name=app_name, slug=slug)
        app_config.save()
    except Exception as e:
        message = f'problem saving data, ``{e}``'
        log.exception(message)
        raise Exception(message)
    log.debug('returning redirect')
    # redirect_url = '/version/'
    redirect_url = reverse('config_slug_url', args=[slug])
    log.debug(f'redirect_url, ``{redirect_url}``')

    response = JsonResponse({'redirect': redirect_url})
    response['HX-Redirect'] = redirect_url
    return response


# -------------------------------------------------------------------
# support urls
# -------------------------------------------------------------------


def error_check(request) -> HttpResponse:
    """
    Offers an easy way to check that admins receive error-emails (in development).
    To view error-emails in runserver-development:
    - run, in another terminal window: `python -m smtpd -n -c DebuggingServer localhost:1026`,
    - (or substitue your own settings for localhost:1026)
    """
    log.debug('\n\nstarting error_check()')
    log.debug(f'project_settings.DEBUG, ``{project_settings.DEBUG}``')
    if project_settings.DEBUG is True:  # localdev and dev-server; never production
        log.debug('triggering exception')
        raise Exception('Raising intentional exception to check email-admins-on-error functionality.')
    else:
        log.debug('returning 404')
        return HttpResponseNotFound('<div>404 / Not Found</div>')


def version(request) -> HttpResponse:
    """
    Returns basic branch and commit data.
    """
    log.debug('\n\nstarting version()')
    rq_now = datetime.datetime.now()
    gatherer = GatherCommitAndBranchData()
    trio.run(gatherer.manage_git_calls)
    info_txt = f'{gatherer.branch} {gatherer.commit}'
    context = version_helper.make_context(request, rq_now, info_txt)
    output = json.dumps(context, sort_keys=True, indent=2)
    log.debug(f'output, ``{output}``')
    return HttpResponse(output, content_type='application/json; charset=utf-8')


def root(request) -> HttpResponseRedirect:
    """
    Redirects to the info page.
    """
    log.debug('\n\nstarting root()')
    return HttpResponseRedirect(reverse('info_url'))
