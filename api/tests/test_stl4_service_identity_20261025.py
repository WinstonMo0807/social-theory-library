"""Deferred inspection of safe service identity; no real service calls."""
from unittest.mock import patch
from catalog.local_services import _check,safe_identity


def test_identity_is_bounded_and_does_not_copy_health_secrets():
    value=safe_identity({"model":"model", "revision":"x"*500,"backend":"onnxruntime-cpu","device":"CPU","runtime_version":"reported",
        "threads":2,"batch_size":True,"loaded":False,"inference_completed":"yes","raw_response":{"secret":"never"},"model_path":"/private/path"})
    assert set(value)=={"model","revision","backend","device","runtime_version","threads","loaded"}
    assert len(value["revision"])==300 and value["loaded"] is False
    assert safe_identity(["malformed"])=={}


def test_service_reports_cpu_from_original_backend_and_retains_completion_separately():
    health={"manifest_ready":True,"backend":"onnxruntime-cpu","runtime_version":"reported","threads":2,"batch_size":4,
        "models":{"embedding":{"model":"baseline","revision":"revision","artifact_id":"identity","loaded":False,"inference_completed":True}},"private":"never"}
    with patch('catalog.services.discovery_inference.inference_health',return_value=health) as call:
        status,_,identity=_check({"id":"discovery-embedding"})
    call.assert_called_once_with(allow_unready=True)
    assert status=='available' and identity['loaded'] is False and identity['inference_completed'] is True
    assert identity['device']=='CPU' and identity['threads']==2 and 'private' not in identity
    health['backend']='other-runtime'
    with patch('catalog.services.discovery_inference.inference_health',return_value=health):
        assert 'device' not in _check({"id":"discovery-embedding"})[2]
