import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class DevicePhoneNumberService {
  const DevicePhoneNumberService({
    MethodChannel? channel,
    bool? isSupportedOverride,
  })  : _channel = channel ?? const MethodChannel(channelName),
        _isSupportedOverride = isSupportedOverride;

  static const String channelName =
      'ai_jurisdiction_mobile/device_phone_number';

  final MethodChannel _channel;
  final bool? _isSupportedOverride;

  bool get _isSupported =>
      _isSupportedOverride ??
      (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  Future<String?> getDevicePhoneNumber() async {
    if (!_isSupported) {
      return null;
    }
    try {
      final value = await _channel.invokeMethod<String>('getDevicePhoneNumber');
      if (value == null) {
        return null;
      }
      final normalized = value.trim().replaceAll(RegExp(r'\s+'), '');
      if (normalized.isEmpty) {
        return null;
      }
      return normalized;
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}
