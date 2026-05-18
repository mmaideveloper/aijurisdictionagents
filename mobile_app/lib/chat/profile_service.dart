import '../auth/local_auth_store.dart';
import 'rule_engine.dart';

typedef ProfilePatchTransport = Future<LocalAuthUser> Function(
  UpdateProfileInput input,
);

class ProfileVoicePatchAudit {
  const ProfileVoicePatchAudit({
    required this.requestedBy,
    required this.changedField,
    required this.newValue,
    required this.timestamp,
    this.previousValue,
  });

  final String requestedBy;
  final String changedField;
  final String? previousValue;
  final String newValue;
  final DateTime timestamp;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'requested_by': requestedBy,
      'changed_field': changedField,
      'previous_value': previousValue,
      'new_value': newValue,
      'timestamp': timestamp.toUtc().toIso8601String(),
      'source': 'voice',
    };
  }
}

class ProfileService {
  ProfileService({
    required ProfilePatchTransport patchTransport,
    DateTime Function()? clock,
  })  : _patchTransport = patchTransport,
        _clock = clock ?? DateTime.now;

  ProfileService.localAuthStore({
    required LocalAuthStore authStore,
    DateTime Function()? clock,
  }) : this(
          patchTransport: (input) => authStore.updateUser(input: input),
          clock: clock,
        );

  final ProfilePatchTransport _patchTransport;
  final DateTime Function() _clock;

  Future<LocalAuthUser> patchProfileFromVoice({
    required LocalAuthUser currentUser,
    required SpokenProfilePatch patch,
    required String requestedBy,
  }) {
    final audit = ProfileVoicePatchAudit(
      requestedBy: requestedBy,
      changedField: patch.apiFieldName,
      previousValue: _currentValue(currentUser, patch.field),
      newValue: patch.value,
      timestamp: _clock(),
    );
    return _patchTransport(
      UpdateProfileInput(
        phoneNumber: currentUser.phoneNumber,
        password: currentUser.password,
        firstName: patch.field == ProfilePatchField.firstName
            ? patch.value
            : currentUser.firstName,
        lastName: patch.field == ProfilePatchField.lastName
            ? patch.value
            : currentUser.lastName,
        address: patch.field == ProfilePatchField.address
            ? patch.value
            : currentUser.address,
        auditPayload: audit.toJson(),
      ),
    );
  }

  String? _currentValue(LocalAuthUser currentUser, ProfilePatchField field) {
    return switch (field) {
      ProfilePatchField.firstName => currentUser.firstName,
      ProfilePatchField.lastName => currentUser.lastName,
      ProfilePatchField.address => currentUser.address,
    };
  }
}
