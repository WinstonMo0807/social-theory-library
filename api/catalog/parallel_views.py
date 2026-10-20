"""Authenticated visibility, without requiring login for public reading."""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .parallel_serializers import (ParallelCandidatesInput, ParallelCandidatesOutput,
    ParallelSegmentsOutput, ParallelSegmentsQuery, ParallelVersionsOutput, ParallelVersionsQuery)
from .services import parallel_reading


class ParallelSourceView(APIView):
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ParallelVersionsView(ParallelSourceView):
    @extend_schema(parameters=[ParallelVersionsQuery], responses=ParallelVersionsOutput)
    def get(self, request):
        query = ParallelVersionsQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(parallel_reading.versions(request.user, **query.validated_data))


class ParallelSegmentsView(ParallelSourceView):
    @extend_schema(parameters=[ParallelSegmentsQuery], responses=ParallelSegmentsOutput)
    def get(self, request):
        query = ParallelSegmentsQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(parallel_reading.segments(request.user, **query.validated_data))


class ParallelCandidatesView(ParallelSourceView):
    def get_throttles(self):
        self.throttle_scope = "exact_search_user" if self.request.user.is_authenticated else "exact_search_anon"
        return super().get_throttles()

    @extend_schema(request=ParallelCandidatesInput, responses=ParallelCandidatesOutput)
    def post(self, request):
        command = ParallelCandidatesInput(data=request.data)
        command.is_valid(raise_exception=True)
        return Response(parallel_reading.candidates(request.user, **command.validated_data))
