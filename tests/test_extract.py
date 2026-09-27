"""Resume extraction layouts, using only synthetic documents."""

import pytest
from docx import Document

from job_agent.tailor.career_facts import load_career_facts
from job_agent.tailor.extract import build_career_facts, extract_career_facts, write_career_facts


def resume(tmp_path, paragraphs):
    doc = Document()
    for text, bold in paragraphs:
        doc.add_paragraph().add_run(text).bold = bold
    path = tmp_path / 'synthetic.docx'
    doc.save(path)
    return path


def test_legacy_layout(tmp_path):
    path = resume(tmp_path, [
        ('Casey Example', True), ('Data Engineer', False),
        ('TECHNICAL SKILLS', True), ('Languages', True), ('Python, SQL', False),
        ('EDUCATION', True), ('Example College', False),
        ('WORK EXPERIENCE', True),
        ("Example Labs's | Remote | Data Engineer  Jan 2020 - Present", True),
        ('Reporting platform.', False), ('Key Responsibilities', True),
        ('Reduced latency by 25%; served 200 users.', False),
        ('Environment: Python, Service (A, B), SQL', False),
        ('Sample Works | Sample City | Analyst  Feb 2018 – Dec 2019', True),
        ('Analytics.', False), ('Key Responsibilities', True), ('Built reports.', False),
    ])
    facts = extract_career_facts(path)
    assert facts['name'] == 'Casey Example'
    assert facts['role'] == 'Data Engineer'
    assert facts['education'] == ['Example College']
    assert facts['skills_inventory'] == {'Languages': ['Python, SQL']}
    assert 'projects' not in facts
    assert facts['employers'][0] == {
        'company': 'Example Labs', 'location': 'Remote', 'title': 'Data Engineer',
        'duration': 'Jan 2020 - Present', 'project_description': 'Reporting platform.',
        'real_bullets': ['Reduced latency by 25%; served 200 users.'],
        'real_metrics': ['Reduced latency by 25%', 'served 200 users'],
        'real_skills': ['Python', 'Service (A, B)', 'SQL'],
    }
    assert facts['employers'][1]['real_bullets'] == ['Built reports.']


@pytest.mark.parametrize('skills_heading', ['SKILLS', 'TECHNICAL SKILLS'])
@pytest.mark.parametrize('work_heading', ['EXPERIENCE', 'WORK EXPERIENCE'])
def test_split_entries_inline_skills_and_projects(tmp_path, skills_heading, work_heading):
    path = resume(tmp_path, [
        ('Casey Example', True), ('Developer', False),
        ('EDUCATION', True), ('Example College\tMay 2017', True),
        ('B.A. Computer Science', False),
        (skills_heading, True),
        ('• Languages: Python, SQL', False),
        ('• AI/ML: Classification, Evaluation', False),
        ('• Cloud & Software Development: Containers, API design', False),
        ('• Tools & Frameworks: Widget (A, B), ExampleKit', False),
        (work_heading, True),
        ('Example Labs\tJanuary 2021 - Present', True),
        ('Software Developer\tSample City, ZZ', False),
        ('Built a queue serving 400 users.', False), ('Maintained tests.', False),
        ('Sample Works\tFeb. 2018 – Dec. 2020', True),
        ('Platform Engineer\tRemote', False), ('Improved monitoring.', False),
        ('PROJECTS', True), ('Paper Kite - Task planner\t2022', True),
        ('Built a scheduling prototype.', False),
        ('Map Lantern\t2019 - 2020', True), ('Added route previews.', False),
    ])
    facts = build_career_facts(path, email='casey@example.invalid', phone='')
    assert facts['education'] == ['Example College\tMay 2017', 'B.A. Computer Science']
    assert facts['skills_inventory'] == {
        'Languages': ['Python', 'SQL'], 'AI/ML': ['Classification', 'Evaluation'],
        'Cloud & Software Development': ['Containers', 'API design'],
        'Tools & Frameworks': ['Widget (A, B)', 'ExampleKit'],
    }
    assert len(facts['employers']) == 2
    assert facts['employers'][0] == {
        'company': 'Example Labs', 'title': 'Software Developer',
        'location': 'Sample City, ZZ', 'duration': 'January 2021 - Present',
        'project_description': '',
        'real_bullets': ['Built a queue serving 400 users.', 'Maintained tests.'],
        'real_metrics': ['Built a queue serving 400 users'], 'real_skills': [],
    }
    assert facts['employers'][1]['real_bullets'] == ['Improved monitoring.']
    assert facts['projects'] == [
        {'header': 'Paper Kite - Task planner\t2022',
         'real_bullets': ['Built a scheduling prototype.']},
        {'header': 'Map Lantern\t2019 - 2020', 'real_bullets': ['Added route previews.']},
    ]
    loaded = load_career_facts(write_career_facts(facts, tmp_path / 'synthetic.yaml'))
    assert loaded.model_dump(mode='json')['projects'] == facts['projects']
    assert isinstance(loaded.projects, tuple)
    assert isinstance(loaded.projects[0].real_bullets, tuple)
    with pytest.raises(ValueError):
        loaded.projects[0].header = 'Changed'


@pytest.mark.parametrize('contact', [
    'casey@example.invalid',
    '(202) 555-0147',
    '+1 202-555-0147',
    '2025550147',
    'https://www.linkedin.com/in/casey-example',
    'github.com/casey-example',
    'Sample City | Portfolio | Contact',
    'Sample City | casey@example.invalid | (202) 555-0147',
])
def test_contact_line_is_not_role(tmp_path, contact):
    path = resume(tmp_path, [
        ('Casey Example', True), (contact, False), ('SKILLS', True),
        ('Languages: Python', False),
    ])
    assert extract_career_facts(path)['role'] == ''


@pytest.mark.parametrize('role', ['Software Developer', 'Engineer II', 'Developer | Data Tools'])
def test_real_role_is_preserved(tmp_path, role):
    path = resume(tmp_path, [('Casey Example', True), (role, False)])
    assert extract_career_facts(path)['role'] == role


def test_section_heading_is_not_role(tmp_path):
    path = resume(tmp_path, [('Casey Example', True), ('SUMMARY', True)])
    assert extract_career_facts(path)['role'] == ''


def test_inline_skills_with_mixed_runs_and_no_education(tmp_path):
    doc = Document()
    doc.add_paragraph('Casey Example')
    doc.add_paragraph('Developer')
    doc.add_paragraph('SKILLS')
    p = doc.add_paragraph()
    p.add_run('• Languages: ').bold = True
    p.add_run('Python, SQL')
    doc.add_paragraph('PROJECTS')
    doc.add_paragraph().add_run('Practice App').bold = True
    doc.add_paragraph('SKILLS improved through practice.')
    path = tmp_path / 'synthetic.docx'
    doc.save(path)
    facts = extract_career_facts(path)
    assert facts['skills_inventory'] == {'Languages': ['Python', 'SQL']}
    assert facts['education'] == []
    assert facts['employers'] == []
    assert facts['projects'][0]['real_bullets'] == ['SKILLS improved through practice.']


@pytest.mark.parametrize('heading', ['SUMMARY', 'PROFESSIONAL SUMMARY:'])
@pytest.mark.parametrize('following', [[], [('SKILLS', True), ('Languages: Python', False)]])
def test_summary_preserved_verbatim(tmp_path, heading, following):
    lines = ['  Builds reliable tools.  ', '', 'Tests\tcarefully.\nDocuments results.']
    path = resume(tmp_path, [
        ('Casey Example', True), ('Developer', False), (heading, True),
        *[(line, False) for line in lines], *following,
    ])
    expected = '\n'.join(lines)
    assert extract_career_facts(path)['summary'] == expected
    assert build_career_facts(path, email='', phone='')['summary'] == expected
    assert build_career_facts(path, email='', phone='', summary='')['summary'] == ''
    assert build_career_facts(
        path, email='', phone='', summary='Explicit approved summary.',
    )['summary'] == 'Explicit approved summary.'


@pytest.mark.parametrize('sequence_type', [list, tuple])
@pytest.mark.parametrize('flag', [True, False, None])
def test_candidate_facts_round_trip(tmp_path, sequence_type, flag):
    path = resume(tmp_path, [
        ('Casey Example', True), ('Developer', False),
        ('WORK EXPERIENCE', True),
        ('Example Labs | Remote | Developer  Jan 2020 - Present', True),
    ])
    supplied = {
        'summary': 'Builds test tools.', 'gpa': '3.70', 'citizenship': 'Exampleland',
        'requires_sponsorship': flag, 'open_to_relocation': flag, 'open_to_remote': flag,
        'honors': sequence_type(['Example College Award']),
        'credentials': sequence_type(['Example Training Credential']),
        'academic_focus': sequence_type(['Distributed systems', 'Database design']),
        'leadership': sequence_type(['Coordinated the example robotics club']),
        'known_gaps': sequence_type(['No production container experience']),
        'notes': sequence_type(['Confirm availability before scheduling']),
    }
    facts = build_career_facts(path, email='casey@example.invalid', phone='', **supplied)
    loaded = load_career_facts(write_career_facts(facts, tmp_path / 'synthetic.yaml'))
    for field, value in supplied.items():
        assert getattr(loaded, field) == (tuple(value) if isinstance(value, (list, tuple)) else value)


def test_candidate_facts_are_not_inferred(tmp_path):
    path = resume(tmp_path, [('Casey Example', True), ('Developer', False)])
    facts = build_career_facts(path, email='', phone='')
    assert facts['summary'] == ''
    for field in ('gpa', 'citizenship', 'requires_sponsorship', 'open_to_relocation', 'open_to_remote'):
        assert facts[field] is None
    assert facts['honors'] == []
    assert facts['credentials'] == []
    for field in ('academic_focus', 'leadership', 'known_gaps', 'notes'):
        assert facts[field] == []


@pytest.mark.parametrize('clause', [
    'Saved 8+ hours per week through report automation',
    'Mentored 24+ student-athletes in the example tutoring program',
    'Saved 8 hours per week through report automation',
    'Mentored 24 student-athletes in the example tutoring program',
    'Reduced latency by 25%',
    'Supported 1,200+ daily users',
    'Served 200 users',
    'Provided support for 3 years',
    'Maintained 12 applications',
    'Processed 5,000 records',
    'Reduced runtime from minutes to seconds',
    'Tripled throughput',
])
def test_metric_clauses_preserved_from_synthetic_resume(tmp_path, clause):
    path = resume(tmp_path, [
        ('Casey Example', True), ('Developer', False), ('EXPERIENCE', True),
        ('Example Labs\tJan 2020 - Present', True), ('Developer\tRemote', False),
        (f'{clause}; Maintained documentation.', False), (f'{clause}.', False),
    ])
    facts = extract_career_facts(path)
    assert facts['employers'][0]['real_metrics'] == [clause]


@pytest.mark.parametrize('bullet', [
    'Used Python 3',
    'Joined the team in 2021',
    'Worked on version 8+',
    'Read chapter 24',
    'Reviewed 8 weekly reports',
    'Documented 24 student-athleteship examples',
    'Reviewed 8 hours per weekday of logs',
])
def test_unrelated_numbers_are_not_metrics(bullet):
    from job_agent.tailor.extract import _metric_clauses

    assert _metric_clauses([bullet]) == []
