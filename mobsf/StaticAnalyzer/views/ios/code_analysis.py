import logging
from pathlib import Path
from enum import Enum

from django.conf import settings

from mobsf.MalwareAnalyzer.views.MalwareDomainCheck import (
    MalwareDomainCheck,
)
from mobsf.StaticAnalyzer.views.common.shared_func import (
    url_n_email_extract,
)
from mobsf.StaticAnalyzer.views.sast_engine import SastEngine
from mobsf.MobSF.utils import (
    append_scan_status,
)

logger = logging.getLogger(__name__)


class _SourceType(Enum):
    swift = 'Swift'
    objc = 'Objective-C'
    swift_and_objc = 'Swift, Objective-C'
    nocode = 'No Code'


def merge_findings(swift, objc):
    code_analysis = {}
    # Add all unique keys
    for k in swift:
        if k in objc:
            swift[k]['files'].update(objc[k]['files'])
        code_analysis[k] = swift[k]
    for k in objc:
        if k not in code_analysis:
            code_analysis[k] = objc[k]
    return code_analysis


def ios_source_analysis(checksum, src):
    """IOS Objective-C and Swift Code Analysis."""
    try:
        logger.info('Starting iOS Source Code and PLIST Analysis')
        root = Path(settings.BASE_DIR) / 'StaticAnalyzer' / 'views'
        swift_rules = root / 'ios' / 'rules' / 'swift_rules.yaml'
        objective_c_rules = root / 'ios' / 'rules' / 'objective_c_rules.yaml'
        api_rules = root / 'ios' / 'rules' / 'ios_apis.yaml'
        code_findings = {}
        api_findings = {}
        email_n_file = []
        url_n_file = []
        url_list = []
        domains = {}
        source_type = ''
        source_types = set()
        skp = settings.SKIP_CLASS_PATH
        msg = 'iOS Source Code Analysis Started'
        logger.info(msg)
        append_scan_status(checksum, msg)

        # Objective C Analysis
        options = {
            'match_rules': objective_c_rules.as_posix(),
            'match_extensions': {'.m'},
            'ignore_paths': skp,
        }
        objc_findings = SastEngine(options, src).scan()
        if objc_findings:
            source_types.add(_SourceType.objc)

        # Swift Analysis
        options = {
            'match_rules': swift_rules.as_posix(),
            'match_extensions': {'.swift'},
            'ignore_paths': skp,
        }
        swift_findings = SastEngine(options, src).scan()
        if swift_findings:
            source_types.add(_SourceType.swift)
        code_findings = merge_findings(swift_findings, objc_findings)
        msg = 'iOS Source Code Analysis Completed'
        logger.info(msg)
        append_scan_status(checksum, msg)

        # API Analysis
        msg = 'iOS API Analysis Started'
        logger.info(msg)
        append_scan_status(checksum, msg)
        options = {
            'match_rules': api_rules.as_posix(),
            'match_extensions': {'.m', '.swift'},
            'ignore_paths': skp,
        }
        api_findings = SastEngine(options, src).scan()
        msg = 'iOS API Analysis Completed'
        logger.info(msg)
        append_scan_status(checksum, msg)

        # Extract URLs and Emails
        msg = 'Extracting Emails and URLs from Source Code'
        logger.info(msg)
        append_scan_status(checksum, msg)
        for pfile in Path(src).rglob('*'):
            if (
                (pfile.suffix in ('.m', '.swift')
                    and any(skip_path in pfile.as_posix()
                            for skip_path in skp) is False
                    and pfile.is_file())
            ):
                content = None
                try:
                    content = pfile.read_text('utf-8', 'ignore')
                    # Certain file path cannot be read in windows
                except Exception:
                    continue
                relative_src_path = pfile.as_posix().replace(src, '')
                urls, urls_nf, emails_nf = url_n_email_extract(
                    content, relative_src_path)
                url_list.extend(urls)
                url_n_file.extend(urls_nf)
                email_n_file.extend(emails_nf)
        msg = 'Email and URL Extraction Completed'
        logger.info(msg)
        append_scan_status(checksum, msg)
        if not source_types:
            source_type = _SourceType.nocode.value
        elif len(source_types) > 1:
            source_type = _SourceType.swift_and_objc.value
        else:
            source_type = source_types.pop().value

        urls_list = list(set(url_list))
        # Domain Extraction and Malware Check
        domains = MalwareDomainCheck().scan(
            checksum,
            urls_list)
        msg = 'Finished Code Analysis, Email and URL Extraction'
        logger.info(msg)
        append_scan_status(checksum, msg)
        code_analysis_dict = {
            'api': api_findings,
            'code_anal': code_findings,
            'urls_list': urls_list,
            'urlnfile': url_n_file,
            'domains': domains,
            'emailnfile': email_n_file,
            'source_type': source_type,
        }
        return code_analysis_dict
    except Exception as exp:
        msg = 'iOS Source Analysis Failed'
        logger.exception(msg)
        append_scan_status(checksum, msg, repr(exp))
