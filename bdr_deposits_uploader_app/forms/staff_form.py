import logging
import pprint

from django import forms
from django.conf import settings

log = logging.getLogger(__name__)


class StaffForm(forms.Form):
    ## Basics section -----------------------------------------------
    collection_pid = forms.CharField(required=True, label='Collection PID')
    collection_title = forms.CharField(required=True, label='Collection Title', help_text='PID sanity-check')
    staff_to_notify = forms.CharField(
        required=True,
        label='Staff to notify on ingest',
        help_text='email1 | email2 | ...',
    )

    authorized_student_groups = forms.CharField(
        required=False,
        label='Authorized student groups',
        help_text='group:A | group:B | ...',
        widget=forms.Textarea(
            attrs={'rows': 5}
        ),  # or I could say widget=forms.Textarea(attrs={'class': 'textarea'}), and then style it in css
    )
    authorized_student_emails = forms.CharField(
        required=False,
        label='Authorized student emails',
        help_text='email1 | email2 | ...',
        widget=forms.Textarea(attrs={'rows': 5}),
    )

    ## Form section - Collaborators ---------------------------------
    offer_advisors_and_readers = forms.BooleanField(required=False, label='Offer advisors/readers')
    advisors_and_readers_required = forms.BooleanField(
        required=False, label='Advisors/readers required', help_text='auto-selects `Offer...` on save'
    )

    offer_team_members = forms.BooleanField(required=False, label='Offer team members')
    team_members_required = forms.BooleanField(
        required=False, label='Team members required', help_text='auto-selects `Offer...` on save'
    )

    offer_faculty_mentors = forms.BooleanField(required=False, label='Offer faculty mentors')
    faculty_mentors_required = forms.BooleanField(
        required=False, label='Faculty mentors required', help_text='auto-selects `Offer...` on save'
    )

    offer_authors = forms.BooleanField(required=False, label='Offer authors')
    authors_required = forms.BooleanField(
        required=False, label='Authors required', help_text='auto-selects `Offer...` on save'
    )

    ## Form section - Department ------------------------------------
    offer_department = forms.BooleanField(required=False, label='Offer Department input')
    department_required = forms.BooleanField(
        required=False, label='Department required', help_text='auto-selects `Offer...` on save'
    )

    offer_research_program = forms.BooleanField(required=False, label='Offer Research Program')
    research_program_required = forms.BooleanField(
        required=False, label='Research Program required', help_text='auto-selects `Offer...` on save'
    )

    ## Form section - Access ----------------------------------------
    offer_embargo_access = forms.BooleanField(required=False, label='Offer 2-year embargo')

    offer_license_options = forms.BooleanField(required=False, label='Offer license options')
    license_required = forms.BooleanField(
        required=False, label='License required', help_text='auto-selects `Offer...` on save'
    )
    license_options = forms.MultipleChoiceField(
        required=False, label='License Options', choices=settings.ALL_LICENSE_OPTIONS
    )
    license_default_choices = [('ERR', 'Unselected')] + settings.ALL_LICENSE_OPTIONS
    license_default = forms.ChoiceField(
        choices=license_default_choices,
        label='License default',
        required=False,
        help_text='select default license',
    )

    offer_visibility_options = forms.BooleanField(required=False, label='Offer visibility options')
    visibility_required = forms.BooleanField(
        required=False, label='Visibility required', help_text='auto-selects `Offer...` on save'
    )
    visibility_options = forms.MultipleChoiceField(
        required=False, label='Visibility Options', choices=settings.ALL_VISIBILITY_OPTIONS
    )
    visibility_default_choices = [('ERR', 'Unselected')] + settings.ALL_VISIBILITY_OPTIONS
    visibility_default = forms.ChoiceField(
        choices=visibility_default_choices, label='Visibility Default', required=False, help_text='select default visibility'
    )

    ## Form section - Other -----------------------------------------
    ask_for_concentrations = forms.BooleanField(required=False, label='Ask for concentrations')
    concentrations_required = forms.BooleanField(
        required=False, label='Concentrations required', help_text='auto-selects `Ask...` on save'
    )

    ask_for_degrees = forms.BooleanField(required=False, label='Ask for degrees')
    degrees_required = forms.BooleanField(
        required=False, label='Degrees required', help_text='auto-selects `Ask...` on save'
    )

    invite_supplementary_files = forms.BooleanField(required=False, label='Invite supplementary files')

    def clean(self):
        log.debug('starting StaffForm.clean()')
        cleaned_data = super().clean()
        log.debug(f'type(cleaned_data): {type(cleaned_data)}')

        ## if a required field is True but the corresponding offer field is not, update the offer field in cleaned_data to True.

        ## collaborators --------------------------------------------
        if cleaned_data.get('advisors_and_readers_required') and not cleaned_data.get('offer_advisors_and_readers'):
            cleaned_data['offer_advisors_and_readers'] = True
        if cleaned_data.get('team_members_required') and not cleaned_data.get('offer_team_members'):
            cleaned_data['offer_team_members'] = True
        if cleaned_data.get('faculty_mentors_required') and not cleaned_data.get('offer_faculty_mentors'):
            cleaned_data['offer_faculty_mentors'] = True
        if cleaned_data.get('authors_required') and not cleaned_data.get('offer_authors'):
            cleaned_data['offer_authors'] = True
        ## department / programs ------------------------------------
        if cleaned_data.get('department_required') and not cleaned_data.get('offer_department'):
            cleaned_data['offer_department'] = True
        if cleaned_data.get('research_program_required') and not cleaned_data.get('offer_research_program'):
            cleaned_data['offer_research_program'] = True
        ## access ---------------------------------------------------
        if cleaned_data.get('license_required') and not cleaned_data.get('offer_license_options'):
            cleaned_data['offer_license_options'] = True
        if cleaned_data.get('visibility_required') and not cleaned_data.get('offer_visibility_options'):
            cleaned_data['offer_visibility_options'] = True
        ## other ----------------------------------------------------
        if cleaned_data.get('concentrations_required') and not cleaned_data.get('ask_for_concentrations'):
            cleaned_data['ask_for_concentrations'] = True
        if cleaned_data.get('degrees_required') and not cleaned_data.get('ask_for_degrees'):
            cleaned_data['ask_for_degrees'] = True

        ## validate that when options are offered, at least one option is selected.

        if cleaned_data.get('offer_license_options'):
            if not cleaned_data.get('license_options'):
                self.add_error('license_options', 'At least one license must be selected.')
            if not cleaned_data.get('license_default'):
                self.add_error('license_default', 'A default license is required.')
            log.debug(f'selected license options: {cleaned_data.get("license_options", "")}')
            log.debug(f'license_default: {cleaned_data.get("license_default", "")}')
            if cleaned_data.get('license_default', '') not in cleaned_data.get('license_options', ''):
                self.add_error('license_default', 'Default license must be one of the selected license options.')
        if cleaned_data.get('license_options') and not cleaned_data.get('offer_license_options'):
            self.add_error('offer_license_options', 'License options must be offered if selected.')
        if cleaned_data.get('license_default') and not cleaned_data.get('offer_license_options'):
            self.add_error('offer_license_options', 'License options must be offered if a default license is selected.')

        if cleaned_data.get('offer_visibility_options'):
            if not cleaned_data.get('visibility_options'):
                self.add_error('visibility_options', 'At least one visibility-option must be selected.')
            if not cleaned_data.get('visibility_default'):
                self.add_error('visibility_default', 'A default visibility-option is required.')
            if cleaned_data.get('visibility_default', '') not in cleaned_data.get('visibility_options', ''):
                self.add_error(
                    'visibility_default', 'Default visibility-option must be one of the selected visibility-options.'
                )
        if cleaned_data.get('visibility_options') and not cleaned_data.get('offer_visibility_options'):
            self.add_error('offer_visibility_options', 'Visibility options must be offered if selected.')
        if cleaned_data.get('visibility_default') and not cleaned_data.get('offer_visibility_options'):
            self.add_error(
                'offer_visibility_options', 'Visibility options must be offered if a default visibility is selected.'
            )

        ## other validation -----------------------------------------
        ## TODO- VALIDATE COLLECTION_TITLE

        ## if nothing is filled out, raise an error
        if not any(
            [
                cleaned_data.get('offer_advisors_and_readers'),
                cleaned_data.get('offer_team_members'),
                cleaned_data.get('offer_faculty_mentors'),
                cleaned_data.get('offer_authors'),
                cleaned_data.get('offer_department'),
                cleaned_data.get('offer_research_program'),
                cleaned_data.get('offer_embargo_access'),
                cleaned_data.get('offer_license_options'),
                cleaned_data.get('offer_access_options'),
                cleaned_data.get('offer_visibility_options'),
                cleaned_data.get('ask_for_concentrations'),
                cleaned_data.get('ask_for_degrees'),
                cleaned_data.get('invite_supplementary_files'),
                cleaned_data.get('authorized_student_groups'),
                cleaned_data.get('authorized_student_emails'),
            ]
        ):
            self.add_error(None, 'At least one field must be filled out.')

        log.debug(f'cleaned_data: {pprint.pformat(cleaned_data)}')
        return cleaned_data

        ## end def clean()

    ## end class StaffForm()
