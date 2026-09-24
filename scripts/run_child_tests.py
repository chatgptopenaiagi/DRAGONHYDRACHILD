"""Run all applicable CHILD tests; never execute donor database mutation tests.

Portable CI remains a separate guarded process. This local runner adds CHILD
SQL/MariaDB/XAMPP and the unchanged compute tests, and reports each inherited
donor fixture test outside CHILD scope instead of counting it as passed/skipped.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

from run_ci import ROOT, RecordingResult, classify, flatten, syntax_and_metadata


def main():
    if sys.version_info[:2] != (3,14):
        raise SystemExit('Python 3.14 is mandatory')
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
    syntax_and_metadata()
    all_tests=list(flatten(unittest.TestLoader().discover(str(ROOT/'tests'))))
    portable,local=classify(unittest.TestSuite(all_tests))
    selected=list(flatten(portable))
    allowed={'test_compute.ComputeBaselineTests','test_child_storage.ChildStorageLiveTests',
             'test_child_runtime.ChildRuntimeLiveTests'}
    extra=[test for test in all_tests if test.id().rsplit('.',1)[0] in allowed]
    selected.extend(extra)
    excluded={test_id: 'NOT_APPLICABLE_TO_CHILD: inherited donor deployment/credential fixture; retained unchanged. '+reason
              for test_id,reason in local.items() if test_id.rsplit('.',1)[0] not in allowed}
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(unittest.TestSuite(selected))
    checkpoint=ROOT/'runtime/checkpoints'/('child-full-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    checkpoint.mkdir(parents=True,exist_ok=False)
    summary={'checked_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,
             'portable_count':len(selected)-len(extra),'local_integration_count':len(extra),
             'tests_run':result.testsRun,'tests_passed':len(result.passed_ids),
             'tests_failed':len(result.failures),'tests_errored':len(result.errors),
             'tests_skipped':len(result.skipped),'passed_ids':result.passed_ids,
             'failed_ids':[test.id() for test,_ in result.failures],
             'errored_ids':[test.id() for test,_ in result.errors],
             'donor_tests_not_applicable':excluded,
             'successful':result.wasSuccessful() and not result.skipped}
    (checkpoint/'tests.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in summary.items() if not key.endswith('_ids') and key!='donor_tests_not_applicable'},indent=2))
    print('LOCAL EVIDENCE PATH: '+str(checkpoint.relative_to(ROOT)))
    return 0 if summary['successful'] else 1


if __name__=='__main__':
    raise SystemExit(main())
