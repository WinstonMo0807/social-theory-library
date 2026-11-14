"""Growing media stays bounded, reproducible and behind the selected publication."""
from hashlib import sha256
from io import BytesIO
from datetime import timedelta
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from catalog.models import MediaRendition, RecommendationIssue, EditorialRevision
from catalog.services.media import build_rendition, ingest_image, prepare_rendition_sizes, update_media_metadata
from PIL import Image

pytestmark = pytest.mark.django_db

def source(actor):
    data=BytesIO();Image.new('RGB',(1600,1000),'#d5bb88').save(data,format='PNG')
    return ingest_image(SimpleUploadedFile('source.png',data.getvalue(),content_type='image/png'),actor=actor,
                        metadata={'credit':'Original credit','alt_text':'Original description'})[0]

def test_preparation_reuses_original_preserves_crop_and_frozen_metadata(settings,tmp_path,admin_user):
    settings.MEDIA_ROOT=tmp_path
    media=source(admin_user)
    crop={'x':0.1,'y':0.2,'width':0.8,'height':0.7,'rotation':90}
    primary=build_rendition(media.pk,width=1280,kind='hero',transform=crop)
    before=(primary.pk,primary.checksum,primary.file.name)
    update_media_metadata(media.pk,actor=admin_user,metadata={'credit':'Unpublished new credit'})
    variants=prepare_rendition_sizes(primary)
    assert {v.requested_width for v in variants}=={320,640,1280}
    assert all(v.metadata_snapshot['credit']=='Original credit' and v.metadata_snapshot['_transform']==crop for v in variants)
    assert all(v.width<=primary.width for v in variants)
    assert all(abs(v.width/v.height-primary.width/primary.height)<0.01 for v in variants)
    assert [v.pk for v in prepare_rendition_sizes(primary)]==[v.pk for v in variants]
    primary.refresh_from_db();assert (primary.pk,primary.checksum,primary.file.name)==before
    with media.file.open('rb') as handle:assert sha256(handle.read()).hexdigest()==media.checksum

def test_old_focal_point_is_not_guessed(settings,tmp_path,admin_user):
    settings.MEDIA_ROOT=tmp_path
    media=source(admin_user);primary=build_rendition(media.pk,width=1280,kind='hero')
    update_media_metadata(media.pk,actor=admin_user,metadata={'focal_x':0.1})
    assert [row.pk for row in prepare_rendition_sizes(primary)]==[primary.pk]
    assert media.renditions.count()==1

def test_new_selection_has_sizes_and_public_variant_requires_current_primary(settings,tmp_path,admin_user,api_client):
    settings.MEDIA_ROOT=tmp_path
    media=source(admin_user)
    api_client.force_authenticate(admin_user)
    response=api_client.post(f'/api/catalog/admin/media/{media.pk}/renditions/',{'kind':'hero','width':1280},format='json')
    assert response.status_code==200
    primary=MediaRendition.objects.get(pk=response.json()['id'])
    variants=prepare_rendition_sizes(primary)
    assert len(variants)==3
    private=build_rendition(media.pk,width=320,kind='portrait')
    now=timezone.now();issue=RecommendationIssue.objects.create(slug='growth-test',title='Draft title',display_from=now-timedelta(days=1))
    revision=EditorialRevision.objects.create(target_type='recommendation_issue',target_id=issue.pk,revision=1,
        idempotency_key='growth-test',status='published',published_at=now,
        materialized_preview={'title':'Published title','body_blocks':[],'items':[],'cover_rendition_id':str(primary.pk)})
    issue.active_revision=revision;issue.save()
    api_client.force_authenticate(None)
    endpoint=f'/api/catalog/editorial-media/{primary.pk}/'
    count=MediaRendition.objects.count()
    for row in variants:
        image=api_client.get(endpoint+f'?rendition={row.pk}')
        assert image.status_code==200
        assert sha256(b''.join(image.streaming_content)).hexdigest()==row.checksum
    assert MediaRendition.objects.count()==count
    assert api_client.get(endpoint+f'?rendition={private.pk}').status_code==404
    assert api_client.get(endpoint+'?rendition=invalid').status_code==404
    assert api_client.get(f'/api/catalog/editorial-media/{variants[0].pk}/').status_code==404
    issue.active_revision=None;issue.save()
    assert api_client.get(endpoint+f'?rendition={variants[0].pk}').status_code==404
