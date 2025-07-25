import logging

from django.template.loader import get_template
from lxml import etree
from lxml.etree import XMLSyntaxError

from bdr_uploader_hub_app.models import Submission

log = logging.getLogger(__name__)


class ModsMaker:
    def __init__(self, submission: Submission):
        self.submission: Submission = submission

    def prepare_mods(self) -> str:
        """
        Manages the creation of the mods xml file.
        """
        log.debug('prepare_mods called')
        title = self.submission.title
        abstract = self.submission.abstract

        ## originInfo -----------------------------------------------
        year_created = str(self.submission.created_at.year)  # W3CDTF year
        date_created = self.submission.created_at.strftime('%Y-%m-%d')  # W3CDTF date

        ## authors --------------------------------------------------
        author_data: str = self.submission.authors or ''
        authors: list[str] = [author.strip() for author in author_data.split('|')] if author_data else []
        log.debug(f'authors: {authors}')

        ## advisors/readers -----------------------------------------
        advisor_reader_data: str = self.submission.advisors_and_readers or ''
        advisor_reader_names: list[str] = (
            [name.strip() for name in advisor_reader_data.split('|')] if advisor_reader_data else []
        )
        log.debug(f'advisor_reader_names: {advisor_reader_names}')

        ## keywords --------------------------------------------------
        keywords_data: str = self.submission.keywords or ''
        keywords: list[str] = [keyword.strip() for keyword in keywords_data.split('|')] if keywords_data else []
        log.debug(f'keywords: {keywords}')

        ## concentrations -------------------------------------------
        concentration_data: str = self.submission.concentrations or ''
        concentrations: list[str] = (
            [concentration.strip() for concentration in concentration_data.split('|')] if concentration_data else []
        )
        log.debug(f'concentrations: {concentrations}')

        ## degrees --------------------------------------------------
        degree_data: str = self.submission.degrees or ''
        degrees: list[str] = [degree.strip() for degree in degree_data.split('|')] if degree_data else []
        log.debug(f'degrees: {degrees}')

        ## departments ----------------------------------------------
        department_data: str = self.submission.department or ''
        departments: list[str] = [department.strip() for department in department_data.split('|')] if department_data else []
        updated_departments: list[str] = []
        for department in departments:
            if 'Brown University' not in department:
                updated_departments.append(f'{department}, Brown University')
            else:
                updated_departments.append(department)
        log.debug(f'updated_departments: {updated_departments}')

        ## faculty mentors --------------------------------------------
        faculty_mentor_data: str = self.submission.faculty_mentors or ''
        faculty_mentors: list[str] = (
            [faculty_mentor.strip() for faculty_mentor in faculty_mentor_data.split('|')] if faculty_mentor_data else []
        )
        log.debug(f'faculty_mentors: {faculty_mentors}')

        ## team members --------------------------------------------
        team_member_data: str = self.submission.team_members or ''
        team_members: list[str] = (
            [team_member.strip() for team_member in team_member_data.split('|')] if team_member_data else []
        )
        log.debug(f'team_members: {team_members}')

        ## accessCondition -------------------------------------------
        selected_license: str = self.submission.license_options or ''
        log.debug(f'selected_license: {selected_license}')

        ## assembling data -------------------------------------------
        context = {
            'title': title,
            'abstract': abstract,
            'authors': authors,
            'advisor_reader_names': advisor_reader_names,
            'keywords': keywords,
            'concentrations': concentrations,
            'degrees': degrees,
            'year_created': year_created,
            'date_created': date_created,
            'departments': updated_departments,
            'faculty_mentors': faculty_mentors,
            'team_members': team_members,
            'selected_license': selected_license,
        }
        ## render the template ---------------------------------------
        template = get_template('mods_base.xml')
        mods_xml: str = template.render(context)
        log.debug(f'mods_xml: ``{mods_xml}``')

        ## validate the xml ------------------------------------------
        self.validate_xml(mods_xml)

        ## format the xml --------------------------------------------
        formatted_xml: str = self.format_xml(mods_xml)
        log.debug(f'formatted_xml: ``{formatted_xml}``')

        ## return the formatted xml ----------------------------------
        return formatted_xml

        ## end def prepare_mods()

    def validate_xml(self, xml: str) -> None:
        """
        Validates the XML string using lxml.

        Args:
            xml: XML string to validate

        Raises:
            ValueError: If the XML is not well-formed
        """
        log.debug(f'validating xml: ``{xml}``')
        try:
            parser = etree.XMLParser(remove_blank_text=True)
            etree.fromstring(xml.encode('utf-8'), parser=parser)
            return True
        except XMLSyntaxError:
            log.exception('XMLSyntaxError')
            return False

    def format_xml(self, xml: str) -> str:
        """Formats the xml string via lxml.
        I tried formatting with BeautifulSoup, and minidom, but they both had issues; this is perfect for my needs.
        Note that the BDR-API _requires_ the typeOfResource element to be in the format: opening-element -> text -> closing-element -- which this formatting ensures.
        Called by manage_item_mods_creation()"""
        from lxml import etree

        xml_bytes: bytes = xml.encode('utf-8')
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml_bytes, parser=parser)
        xml_formatted = etree.tostring(tree, pretty_print=True).decode()  # type: ignore
        return xml_formatted
