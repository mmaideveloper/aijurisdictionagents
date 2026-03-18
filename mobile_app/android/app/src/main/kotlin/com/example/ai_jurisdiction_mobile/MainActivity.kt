package com.example.ai_jurisdiction_mobile

import android.Manifest
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    companion object {
        private const val APP_UPDATER_CHANNEL = "ai_jurisdiction_mobile/app_updater"
        private const val DEVICE_PHONE_NUMBER_CHANNEL = "ai_jurisdiction_mobile/device_phone_number"
        private const val PHONE_PERMISSION_REQUEST_CODE = 4107
    }

    private var pendingDevicePhoneNumberResult: MethodChannel.Result? = null

    private fun apkSignaturesMatchInstalledApp(apkPath: String): Boolean {
        val archiveFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            @Suppress("DEPRECATION")
            PackageManager.GET_SIGNATURES
        }

        val installedFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES.toLong()
        } else {
            @Suppress("DEPRECATION")
            PackageManager.GET_SIGNATURES.toLong()
        }

        val archiveInfo = packageManager.getPackageArchiveInfo(apkPath, archiveFlags)
            ?: return true

        if (archiveInfo.packageName != packageName) {
            return true
        }

        val installedInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            packageManager.getPackageInfo(
                packageName,
                PackageManager.PackageInfoFlags.of(installedFlags)
            )
        } else {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, installedFlags.toInt())
        }

        return readSigningFingerprints(installedInfo) == readSigningFingerprints(archiveInfo)
    }

    private fun readSigningFingerprints(packageInfo: PackageInfo): Set<String> {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signingInfo = packageInfo.signingInfo ?: return emptySet()
            val signatures = if (signingInfo.hasMultipleSigners()) {
                signingInfo.apkContentsSigners
            } else {
                signingInfo.signingCertificateHistory
            }
            return signatures.map { it.toCharsString() }.toSet()
        }

        @Suppress("DEPRECATION")
        return packageInfo.signatures?.map { it.toCharsString() }?.toSet() ?: emptySet()
    }

    private fun hasDevicePhonePermission(): Boolean {
        return requiredDevicePhonePermissions().any { permission ->
            ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requiredDevicePhonePermissions(): Array<String> {
        val permissions = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            permissions += Manifest.permission.READ_PHONE_NUMBERS
        }
        permissions += Manifest.permission.READ_PHONE_STATE
        return permissions.distinct().toTypedArray()
    }

    private fun requestDevicePhonePermission() {
        ActivityCompat.requestPermissions(
            this,
            requiredDevicePhonePermissions(),
            PHONE_PERMISSION_REQUEST_CODE
        )
    }

    private fun sanitizePhoneNumber(value: String?): String? {
        val normalized = value
            ?.trim()
            ?.replace("\\s+".toRegex(), "")
            ?.takeIf { it.isNotEmpty() }
        return normalized
    }

    private fun readDevicePhoneNumber(): String? {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val subscriptionManager = getSystemService(SubscriptionManager::class.java)
                val subscriptionId = SubscriptionManager.getDefaultSubscriptionId()
                if (subscriptionManager != null &&
                    SubscriptionManager.isValidSubscriptionId(subscriptionId)
                ) {
                    sanitizePhoneNumber(subscriptionManager.getPhoneNumber(subscriptionId))
                        ?.let { return it }
                }
            }

            val telephonyManager = getSystemService(TelephonyManager::class.java)
            sanitizePhoneNumber(telephonyManager?.line1Number)
        } catch (_: SecurityException) {
            null
        } catch (_: RuntimeException) {
            null
        }
    }

    private fun handleGetDevicePhoneNumber(result: MethodChannel.Result) {
        if (pendingDevicePhoneNumberResult != null) {
            result.error("request_in_progress", "Phone number lookup already in progress.", null)
            return
        }
        if (!hasDevicePhonePermission()) {
            pendingDevicePhoneNumberResult = result
            requestDevicePhonePermission()
            return
        }
        result.success(readDevicePhoneNumber())
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            APP_UPDATER_CHANNEL
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "canRequestPackageInstalls" -> {
                    val allowed = Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
                        packageManager.canRequestPackageInstalls()
                    result.success(allowed)
                }

                "openInstallPermissionSettings" -> {
                    val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                        data = Uri.parse("package:$packageName")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(intent)
                    result.success(null)
                }

                "installApk" -> {
                    val filePath = call.argument<String>("filePath")
                    if (filePath.isNullOrBlank()) {
                        result.error("invalid_args", "filePath is required", null)
                        return@setMethodCallHandler
                    }

                    val apkFile = File(filePath)
                    if (!apkFile.exists()) {
                        result.error("not_found", "APK file does not exist: $filePath", null)
                        return@setMethodCallHandler
                    }

                    if (!apkSignaturesMatchInstalledApp(filePath)) {
                        result.error(
                            "signature_mismatch",
                            "The installed app signature differs from the update APK. Uninstall the current app and install the update APK manually.",
                            null
                        )
                        return@setMethodCallHandler
                    }

                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                        !packageManager.canRequestPackageInstalls()
                    ) {
                        result.error(
                            "install_permission_required",
                            "Install unknown apps permission is required.",
                            null
                        )
                        return@setMethodCallHandler
                    }

                    val apkUri = FileProvider.getUriForFile(
                        this,
                        "$packageName.fileprovider",
                        apkFile
                    )
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(apkUri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivity(intent)
                    result.success(null)
                }

                else -> result.notImplemented()
            }
        }

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            DEVICE_PHONE_NUMBER_CHANNEL
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "getDevicePhoneNumber" -> handleGetDevicePhoneNumber(result)
                else -> result.notImplemented()
            }
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        if (requestCode == PHONE_PERMISSION_REQUEST_CODE) {
            val pendingResult = pendingDevicePhoneNumberResult
            pendingDevicePhoneNumberResult = null
            if (pendingResult != null) {
                val granted = grantResults.any { it == PackageManager.PERMISSION_GRANTED }
                pendingResult.success(if (granted) readDevicePhoneNumber() else null)
            }
            return
        }
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
    }
}
