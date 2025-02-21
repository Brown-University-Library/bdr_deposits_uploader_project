import datetime
import json
import logging
import pprint
from pathlib import Path
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
from bdr_deposits_uploader_app.forms.student_form import make_student_form_class
from bdr_deposits_uploader_app.lib import config_new_helper, uploaded_file_handler, version_helper
from bdr_deposits_uploader_app.lib.shib_handler import shib_decorator
from bdr_deposits_uploader_app.lib.version_helper import GatherCommitAndBranchData
from bdr_deposits_uploader_app.models import AppConfig, Submission

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
            full_authenticated_new_url = f'{request.scheme}://{request.get_host()}{reverse("staff_config_new_url")}'
        elif type_value == 'student':
            full_authenticated_new_url = f'{request.scheme}://{request.get_host()}{reverse("student_upload_url")}'
        log.debug(f'full_staff_config_new_url, ``{full_authenticated_new_url}``')
        if request.get_host() == '127.0.0.1:8000':  # eases local development
            redirect_url = full_authenticated_new_url
        else:
            encoded_full_staff_config_new_url = parse.quote(full_authenticated_new_url, safe='')
            redirect_url = f'{project_settings.SHIB_SP_LOGIN_URL}?target={encoded_full_staff_config_new_url}'
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
                resp = redirect(reverse('staff_config_new_url'))
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
                    {'form': form, 'slug': slug, 'app_name': app_config.name, 'username': request.user.first_name},
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
    StudentUploadForm: django.forms.forms.DeclarativeFieldsMetaclass = make_student_form_class(config_data)

    ## handle POST and GET ------------------------------------------
    if request.method == 'POST':
        log.debug('handling POST')
        form = StudentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data.copy()
            log.debug(f'cleaned_data from copy, ``{pprint.pformat(cleaned_data)}``')
            uploaded_file = cleaned_data.get('main_file')
            log.debug(f'type(uploaded_file), ``{type(uploaded_file)}``')
            if uploaded_file:
                cleaned_data['original_file_name'] = uploaded_file.name  # for confirmation-display
                ## save uploaded main-file --------------------------
                saved_path: Path = uploaded_file_handler.handle_uploaded_file(uploaded_file)  # path like `uuid4hex.ext`
                ## make checksum ------------------------------------
                result: tuple[str, str] = uploaded_file_handler.make_checksum(saved_path)
                (checksum_type, checksum) = result
                cleaned_data['checksum_type'] = checksum_type
                cleaned_data['checksum'] = checksum
                ## store uuid-path, not file-obj, in session --------
                cleaned_data['staged_file_path'] = str(saved_path)  # for Submission record, not for confirmation-display
                del cleaned_data['main_file']  # remove the file-obj from the cleaned_data
            request.session['student_form_data'] = cleaned_data
            resp = redirect(reverse('student_confirm_url', kwargs={'slug': slug}))

    else:  # GET
        ## see if there's form session data to pre-populate the form
        initial_data = request.session.get('student_form_data', {})
        form = StudentUploadForm(initial=initial_data)
        request.session['student_form_data'] = {}  # clear the session data
        ## render the form
        form = StudentUploadForm(initial=initial_data)
        resp: HttpResponse = render(
            request,
            'student_form.html',
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


@login_required
def student_confirm(request, slug):
    """
    Displays the student-upload confirmation page.
    """
    log.debug('\n\nstarting student_confirm()')

    ## retrieve stored data from session
    student_data = request.session.get('student_form_data')
    if not student_data:
        ## no data saved; redirect back to upload form
        return redirect(reverse('student_upload_slug_url', kwargs={'slug': slug}))

    if request.method == 'POST':
        if 'confirm' in request.POST:
            ## confirmed, so create Submission record
            app_config = get_object_or_404(AppConfig, slug=slug)
            submission = Submission.objects.create(
                ## basics -------------------------------------------
                app=app_config,
                student_eppn=request.user.username,
                student_email=request.user.email,
                title=student_data.get('title'),
                abstract=student_data.get('abstract'),
                ## collaborators ------------------------------------
                advisors_and_readers=student_data.get('advisors_and_readers'),
                team_members=student_data.get('team_members'),
                faculty_mentors=student_data.get('faculty_mentors'),
                authors=student_data.get('authors'),
                ## departments/programs ------------------------------
                department=student_data.get('department'),
                research_program=student_data.get('research_program'),
                ## access and visibility -----------------------------
                license_options=student_data.get('license_options'),
                visibility_options=student_data.get('visibility_options'),
                ## other --------------------------------------------
                concentrations=student_data.get('concentrations'),
                degrees=student_data.get('degrees'),
                ## file-stuff ---------------------------------------
                primary_file=student_data.get('staged_file_path'),
                supplementary_files=student_data.get('supplementary_files'),
                original_file_name=student_data.get('original_file_name'),
                staged_file_name=student_data.get('staged_file_path').split('/')[-1],
                checksum_type=student_data.get('checksum_type'),
                checksum=student_data.get('checksum'),
                ## form-data ----------------------------------------
                temp_submission_json=student_data,
            )
            log.debug(f'submission created-and-saved successfully, ``{submission}``')
            ## clear the session data after processing
            del request.session['student_form_data']
            return redirect('upload_successful_url')  # redirect to student-form success page
        elif 'edit' in request.POST:
            ## send back to student-upload-form
            return redirect(reverse('student_upload_slug_url', kwargs={'slug': slug}))
    else:
        # Render a template that shows the submitted data read-only.
        context = {
            'student_data': student_data,
            'slug': slug,
            'app_name': get_object_or_404(AppConfig, slug=slug).name,
        }
        return render(request, 'student_confirm.html', context)


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
    redirect_url = reverse('staff_config_slug_url', args=[slug])
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
